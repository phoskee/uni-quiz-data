import fs from "fs";
import path from "path";
import readline from "readline";
import { Readable } from "stream";

// ============================================================================
// MODELLI E TIPI DATI
// ============================================================================

interface ScriptItem {
  name: string;
  script: string;
  description: string;
  detailedDescription: string;
}

interface Question {
  id?: string;
  question: string;
  options: { text: string; image?: string }[];
  correctIndex: number;
  explanation?: string;
  hint?: string;
  code?: string;
}

interface QuizStat {
  path: string;
  rel: string;
  total: number;
  complete: number;
  missing_explanation: number;
  missing_hint: number;
  missing_both: number;
  status: "completo" | "incompleto" | "da fare";
}

const SCRIPTS: ScriptItem[] = [
  {
    name: "Esplora Statistiche e Diagnostica Quiz",
    script: "tui_explorer",
    description: "Esplora lo stato, spiegazioni/indizi mancanti e diagnostica di un quiz.",
    detailedDescription: "Consente di selezionare interattivamente qualsiasi quiz nell'archivio, mostrando statistiche dettagliate su spiegazioni e indizi mancanti, errori strutturali del file JSON e navigazione paginata delle domande."
  },
  {
    name: "Arricchitore di Quiz (Gemini)",
    script: "gemini_enrich_quiz.py",
    description: "Arricchisce spiegazioni e indizi dei quiz tramite Gemini API (TUI TS).",
    detailedDescription: "Utilizza le API di Google Gemini per popolare i campi 'explanation' e 'hint' dei quiz JSON in modo automatico. Esegue il processo in background comandato dalla TUI in TypeScript con pausa e interruzione sicura."
  },
  {
    name: "Arricchitore di Quiz (Ollama)",
    script: "ollama_enrich_quiz.py",
    description: "Arricchisce spiegazioni e indizi dei quiz tramite Ollama locale (TUI TS).",
    detailedDescription: "Utilizza modelli LLM locali in esecuzione su Ollama per arricchire spiegazioni e indizi dei quiz. Esegue il processo in background comandato dalla TUI in TypeScript con pausa e interruzione sicura."
  },
  {
    name: "Generatore di Quiz da PDF",
    script: "generate_quiz.py",
    description: "Estrae e genera quiz in JSON a partire da PDF usando Gemini (TUI TS).",
    detailedDescription: "Estrae il testo dai PDF di input e interroga le API di Google Gemini per generare un quiz strutturato in formato JSON salvato nella cartella community. Il flusso è gestito interattivamente in TypeScript e avviato in modalità headless."
  },
  {
    name: "Validatore di Quiz JSON",
    script: "validate.py",
    description: "Valida la correttezza strutturale e semantica dei file JSON dei quiz.",
    detailedDescription: "Esegue una scansione ricorsiva di tutti i quiz in 'quizzes/' e 'open-questions/' per verificare la conformità allo schema (campi obbligatori, UUID validi ed univoci, correctIndex nei limiti delle opzioni). Usato anche nella CI del progetto."
  },
  {
    name: "Generatore Pacchetti Pubblici",
    script: "build_packs.py",
    description: "Compila i pacchetti dei quiz deterministici privi di spiegazioni/indizi.",
    detailedDescription: "Esporta pacchetti deterministici pronti per la distribuzione pubblica a partire dai quiz in archivio, rimuovendo spiegazioni ed indizi per consentire la verifica di autovalutazione pulita."
  },
  {
    name: "Assegnatore UUID Pubblici",
    script: "assign_public_ids.py",
    description: "Assegna UUID stabili univoci a quiz e domande.",
    detailedDescription: "Scansiona tutti i file dei quiz nell'archivio e assegna in modo stabile e persistente UUID pubblici alle domande e ai quiz che ne sono sprovvisti, registrandoli nel manifest."
  },
  {
    name: "Convertitore PDF Concorso PDS (AG2026)",
    script: "pds_quiz_pdf.py",
    description: "Converte PDF strutturati a scelta multipla nel formato Uni-Quiz.",
    detailedDescription: "Parser specializzato per convertire documenti PDF a doppia colonna con numerazione e opzioni da A) a E) nello schema JSON del progetto (specifico per la banca dati Allievi Agenti Polizia di Stato 2026)."
  }
];

// ============================================================================
// STATO GLOBALE
// ============================================================================

let selectedIdx = 0;
let isRunning = false;

const DIM = "\x1b[2;37m";
const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const CYAN = "\x1b[1;36m";
const GREEN = "\x1b[1;32m";
const RED = "\x1b[1;31m";
const YELLOW = "\x1b[1;33m";

// ============================================================================
// FUNZIONI FILE SYSTEM & STATISTICHE
// ============================================================================

function getJsonFiles(dir: string): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    if (file.startsWith("_")) continue;
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      results.push(...getJsonFiles(fullPath));
    } else if (file.endsWith(".json")) {
      results.push(fullPath);
    }
  }
  return results;
}

function getPdfFiles(dir: string): string[] {
  const results: string[] = [];
  if (!fs.existsSync(dir)) return results;
  const list = fs.readdirSync(dir);
  for (const file of list) {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      results.push(...getPdfFiles(fullPath));
    } else if (file.endsWith(".pdf") && fullPath.split(path.sep).includes("_docs")) {
      results.push(fullPath);
    }
  }
  return results;
}

function scanPDFFiles(): string[] {
  return getPdfFiles("quizzes");
}

function getQuizStats(filePath: string): QuizStat {
  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const data: Question[] = JSON.parse(content);
    let complete = 0;
    let missing_explanation = 0;
    let missing_hint = 0;
    let missing_both = 0;

    for (const q of data) {
      const has_exp = !!q.explanation?.trim();
      const has_hint = !!q.hint?.trim();
      if (has_exp && has_hint) complete++;
      else if (!has_exp && !has_hint) missing_both++;
      else if (!has_exp) missing_explanation++;
      else missing_hint++;
    }

    let status: "completo" | "incompleto" | "da fare" = "da fare";
    if (data.length > 0) {
      if (complete === data.length) status = "completo";
      else if (missing_both === data.length) status = "da fare";
      else status = "incompleto";
    }

    return {
      path: filePath,
      rel: path.relative("quizzes", filePath),
      total: data.length,
      complete,
      missing_explanation,
      missing_hint,
      missing_both,
      status
    };
  } catch {
    return {
      path: filePath,
      rel: path.relative("quizzes", filePath),
      total: 0,
      complete: 0,
      missing_explanation: 0,
      missing_hint: 0,
      missing_both: 0,
      status: "da fare"
    };
  }
}

function checkQuizDiagnostics(quizData: Question[]): string[] {
  const errors: string[] = [];
  const seenIds = new Set<string>();

  for (let idx = 0; idx < quizData.length; idx++) {
    const item = quizData[idx];
    const missingFields: string[] = [];
    if (!item.id) missingFields.push("id");
    if (!item.question) missingFields.push("question");
    if (!item.options) missingFields.push("options");
    if (item.correctIndex === undefined) missingFields.push("correctIndex");

    if (missingFields.length > 0) {
      errors.push(`Domanda all'indice ${idx}: manca di campi obbligatori (${missingFields.join(", ")}).`);
      continue;
    }

    // Unicità UUID
    const qid = String(item.id);
    if (seenIds.has(qid)) {
      errors.push(`Domanda all'indice ${idx}: UUID duplicato '${qid}'.`);
    }
    seenIds.add(qid);

    // Options
    if (!Array.isArray(item.options) || item.options.length === 0) {
      errors.push(`Domanda all'indice ${idx}: deve avere un array 'options' non vuoto.`);
      continue;
    }

    // correctIndex
    if (typeof item.correctIndex !== "number" || !Number.isInteger(item.correctIndex)) {
      errors.push(`Domanda all'indice ${idx}: 'correctIndex' deve essere un intero.`);
    } else if (item.correctIndex < 0 || item.correctIndex >= item.options.length) {
      errors.push(`Domanda all'indice ${idx}: 'correctIndex' non valido (${item.correctIndex}).`);
    }
  }

  return errors;
}

// ============================================================================
// COMPONENTE DIAGNOSTICA ED ESPLORATORE TUI (TS)
// ============================================================================

async function browseQuestionsPaginated(questions: [number, Question, string][], title: string) {
  const pageSize = 2;
  const totalPages = Math.ceil(questions.length / pageSize);
  let currentPage = 0;

  while (true) {
    console.clear();
    console.log(CYAN + "=".repeat(80));
    console.log(` 🔍 ${title} (Pagina ${currentPage + 1} di ${totalPages})`);
    console.log(` Trovate ${questions.length} domande corrispondenti.`);
    console.log("=".repeat(80) + RESET + "\n");

    const startIdx = currentPage * pageSize;
    const endIdx = Math.min(startIdx + pageSize, questions.length);

    for (let i = startIdx; i < endIdx; i++) {
      const [globalIdx, q, issueDesc] = questions[i];
      console.log(` 📌 [DOMANDA ALL'INDICE ${globalIdx}] UUID: ${q.id || "N/D"}`);
      console.log(`  • Problema: ${RED}${issueDesc}${RESET}`);
      console.log(`  • Testo:     ${q.question}`);
      if (q.code) {
        console.log(`    Codice:`);
        for (const line of q.code.split("\n")) {
          console.log(`      ${line}`);
        }
      }
      console.log(`  • Opzioni:`);
      for (let j = 0; j < (q.options?.length || 0); j++) {
        const prefix = j === q.correctIndex ? "  👉" : "    ";
        console.log(`${prefix} ${String.fromCharCode(65 + j)}) ${q.options[j].text || ""}`);
      }

      const exp = String(q.explanation || "").trim();
      const hint = String(q.hint || "").trim();
      console.log(`  • Spiegazione: ${exp ? DIM + exp + RESET : "[Vuota]"}`);
      console.log(`  • Suggerimento: ${hint ? hint : "[Vuoto]"}`);
      console.log(DIM + "-".repeat(80) + RESET);
    }

    console.log("\n COMANDI:");
    console.log("  [N] Pagina successiva  |  [P] Pagina precedente  |  [B] Torna all'esploratore");
    console.log(CYAN + "=".repeat(80) + RESET);

    const cmd = await readSingleChar();
    if (cmd === "b") {
      break;
    } else if (cmd === "n") {
      if (currentPage < totalPages - 1) currentPage++;
    } else if (cmd === "p") {
      if (currentPage > 0) currentPage--;
    }
  }
}

async function exploreQuizTS(filePath: string) {
  let quizData: Question[];
  try {
    quizData = JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch (e) {
    console.log(`\n❌ Errore caricamento quiz: ${e}`);
    await waitReturn();
    return;
  }

  const total = quizData.length;
  const stats = getQuizStats(filePath);
  const structuralErrors = checkQuizDiagnostics(quizData);

  while (true) {
    console.clear();
    console.log(CYAN + "=".repeat(80));
    console.log(` 📊 ESPLORAZIONE E DIAGNOSTICA: ${path.basename(filePath)}`);
    console.log("=".repeat(80) + RESET);
    console.log(` Percorso: ${filePath}\n`);

    console.log(` STATISTICHE DOMANDE:`);
    console.log(`  • Totale domande:             ${total}`);
    if (total > 0) {
      console.log(`  • Complete (Spieg.+Sugger.):   ${stats.complete} (${(stats.complete / total * 100).toFixed(1)}%)`);
      console.log(`  • Incomplete:                 ${total - stats.complete} (${((total - stats.complete) / total * 100).toFixed(1)}%)`);
    } else {
      console.log(`  • Complete:                   0 (0.0%)`);
      console.log(`  • Incomplete:                 0 (0.0%)`);
    }
    console.log(`     - Mancano entrambi:        ${stats.missing_both}`);
    console.log(`     - Manca solo spiegazione:  ${stats.missing_explanation}`);
    console.log(`     - Manca solo suggerimento: ${stats.missing_hint}\n`);

    console.log(` DIAGNOSTICA STRUTTURALE (validate.py):`);
    if (structuralErrors.length > 0) {
      console.log(`  ❌ Rilevati ${structuralErrors.length} errori strutturali:`);
      for (const err of structuralErrors.slice(0, 5)) {
        console.log(`    - ${err}`);
      }
      if (structuralErrors.length > 5) {
        console.log(`    ... e altri ${structuralErrors.length - 5} errori`);
      }
    } else {
      console.log(`  ✅ Nessun errore di struttura rilevato (il file rispetta i campi obbligatori).`);
    }
    console.log(DIM + "-".repeat(80) + RESET);

    console.log(" SCEGLI COSA ESPLORARE:");
    console.log("  [1] Domande con spiegazione mancante");
    console.log("  [2] Domande con suggerimento mancante");
    console.log("  [3] Domande con entrambi mancanti");
    console.log("  [4] Domande con errori strutturali");
    console.log("  [5] Tutte le domande incomplete");
    console.log("\n  [B] Torna indietro");
    console.log(CYAN + "=".repeat(80) + RESET);

    const choice = await readSingleChar();
    if (choice === "b") {
      break;
    }

    let filtered: [number, Question, string][] = [];
    let title = "";

    if (choice === "1") {
      title = "DOMANDE CON SPIEGAZIONE MANCANTE";
      filtered = quizData
        .map((q, idx) => [idx, q, "Manca spiegazione"] as [number, Question, string])
        .filter(([_, q]) => !q.explanation?.trim());
    } else if (choice === "2") {
      title = "DOMANDE CON SUGGERIMENTO MANCANTE";
      filtered = quizData
        .map((q, idx) => [idx, q, "Manca suggerimento"] as [number, Question, string])
        .filter(([_, q]) => !q.hint?.trim());
    } else if (choice === "3") {
      title = "DOMANDE CON ENTRAMBI MANCANTI";
      filtered = quizData
        .map((q, idx) => [idx, q, "Manca spiegazione e suggerimento"] as [number, Question, string])
        .filter(([_, q]) => !q.explanation?.trim() && !q.hint?.trim());
    } else if (choice === "4") {
      title = "DOMANDE CON ERRORI STRUTTURALI";
      const errIndices = new Map<number, string[]>();
      for (const err of structuralErrors) {
        const m = err.match(/all'indice (\d+)/);
        if (m) {
          const idx = parseInt(m[1]);
          if (!errIndices.has(idx)) errIndices.set(idx, []);
          errIndices.get(idx)!.push(err);
        }
      }
      filtered = Array.from(errIndices.keys())
        .sort((a, b) => a - b)
        .map((idx) => [idx, quizData[idx], errIndices.get(idx)!.join("\n")] as [number, Question, string]);
    } else if (choice === "5") {
      title = "TUTTE LE DOMANDE INCOMPLETE";
      filtered = quizData
        .map((q, idx) => {
          const has_exp = !!q.explanation?.trim();
          const has_hint = !!q.hint?.trim();
          const issues: string[] = [];
          if (!has_exp) issues.push("Manca spiegazione");
          if (!has_hint) issues.push("Manca suggerimento");
          return [idx, q, issues.join(" & ")] as [number, Question, string];
        })
        .filter(([_, __, desc]) => desc !== "");
    }

    if (filtered.length === 0) {
      console.log(`\n${GREEN}✅ Nessuna domanda trovata per questo filtro!${RESET}`);
      await sleep(1500);
      continue;
    }

    await browseQuestionsPaginated(filtered, title);
  }
}

// ============================================================================
// COMPONENTE ARRICCHIMENTO GUIDATO (TUI TS + PROCESS BACKEND)
// ============================================================================

async function selectQuizInteractive(): Promise<string | null> {
  const files = getJsonFiles("quizzes");
  if (files.length === 0) {
    console.log("\n❌ Nessun file JSON trovato in quizzes/");
    await waitReturn();
    return null;
  }

  const stats = files.map((f) => getQuizStats(f));
  let idx = 0;

  while (true) {
    console.clear();
    console.log(CYAN + "=".repeat(80));
    console.log(" 📋 SELEZIONE QUIZ (TUI TS)");
    console.log("=".repeat(80) + RESET + "\n");
    console.log(" Scegli il file usando le frecce [↑ / ↓] e premi Invio:\n");

    for (let i = 0; i < stats.length; i++) {
      const isSelected = i === idx;
      const prefix = isSelected ? " ➔ \x1b[1;32m●" : "    \x1b[0;37m○";
      const suffix = isSelected ? RESET : "";
      
      const badge = stats[i].status === "completo" ? "🟢" : stats[i].status === "incompleto" ? "🟡" : "🔴";
      const statsStr = `[${stats[i].complete}/${stats[i].total} | B: ${stats[i].missing_both} | E: ${stats[i].missing_explanation} | H: ${stats[i].missing_hint}]`;
      
      console.log(`${prefix} ${stats[i].rel} ${statsStr}${suffix}`);
    }

    console.log("\n" + CYAN + "=".repeat(80) + RESET);
    console.log(" [Invio] Conferma  |  [Esc / Q] Torna al menu principale");

    const key = await readKeyName();
    if (key === "escape" || key === "q") {
      return null;
    } else if (key === "up") {
      idx = (idx - 1 + stats.length) % stats.length;
    } else if (key === "down") {
      idx = (idx + 1) % stats.length;
    } else if (key === "return") {
      return stats[idx].path;
    }
  }
}

async function selectPDFInteractive(): Promise<string | null> {
  const files = scanPDFFiles();
  if (files.length === 0) {
    console.log("\n❌ Nessun file PDF trovato in quizzes/**/_docs/");
    await waitReturn();
    return null;
  }

  let idx = 0;
  while (true) {
    console.clear();
    console.log(CYAN + "=".repeat(80));
    console.log(" 📄 SELEZIONE DOCUMENTO PDF DA ELABORARE");
    console.log("=".repeat(80) + RESET + "\n");
    console.log(" Scegli il file PDF usando le frecce [↑ / ↓] e premi Invio:\n");

    for (let i = 0; i < files.length; i++) {
      const isSelected = i === idx;
      const prefix = isSelected ? " ➔ \x1b[1;32m●" : "    \x1b[0;37m○";
      const suffix = isSelected ? RESET : "";
      const relPath = path.relative("quizzes", files[i]);
      console.log(`${prefix} ${relPath}${suffix}`);
    }

    console.log("\n" + CYAN + "=".repeat(80) + RESET);
    console.log(" [Invio] Conferma  |  [Esc / Q] Annulla");

    const key = await readKeyName();
    if (key === "escape" || key === "q") {
      return null;
    } else if (key === "up") {
      idx = (idx - 1 + files.length) % files.length;
    } else if (key === "down") {
      idx = (idx + 1) % files.length;
    } else if (key === "return") {
      return files[idx];
    }
  }
}

async function selectModelInteractive(isOllama: boolean): Promise<string | null> {
  let models: string[] = [];
  
  if (isOllama) {
    console.clear();
    console.log("\n📡 Recupero modelli da Ollama (localhost:11434)...");
    try {
      const res = await fetch("http://localhost:11434/api/tags");
      if (res.ok) {
        const data = await res.json() as any;
        const names = data.models?.map((m: any) => m.name) || [];
        models = names.filter((n: string) => n.toLowerCase().includes("cloud"));
        if (models.length === 0) {
          models = names; // fallback
        }
      }
    } catch {
      // Ignora l'errore ed esegui fallback
    }
    
    if (models.length === 0) {
      models = ["llama3.2-cloud", "llama3-cloud", "mistral-cloud", "phi3-cloud"];
    }
  } else {
    // Gemini
    models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"];
  }

  let idx = 0;
  while (true) {
    console.clear();
    console.log(CYAN + "=".repeat(80));
    console.log(isOllama ? " 🧠 SELEZIONE MODELLO OLLAMA (SOLO CLOUD)" : " 🧠 SELEZIONE MODELLO GEMINI");
    console.log("=".repeat(80) + RESET + "\n");
    console.log(" Scegli il modello usando le frecce [↑ / ↓] e premi Invio:\n");

    for (let i = 0; i < models.length; i++) {
      const isSelected = i === idx;
      const prefix = isSelected ? " ➔ \x1b[1;32m●" : "    \x1b[0;37m○";
      const suffix = isSelected ? RESET : "";
      console.log(`${prefix} ${models[i]}${suffix}`);
    }

    console.log("\n" + CYAN + "=".repeat(80) + RESET);
    console.log(" [Invio] Conferma  |  [Esc / Q] Torna al menu principale");

    const key = await readKeyName();
    if (key === "escape" || key === "q") {
      return null;
    } else if (key === "up") {
      idx = (idx - 1 + models.length) % models.length;
    } else if (key === "down") {
      idx = (idx + 1) % models.length;
    } else if (key === "return") {
      return models[idx];
    }
  }
}

async function runEnrichmentHeadless(scriptName: string, quizPath: string, model: string, batchSize: number, withSearch: boolean) {
  console.clear();
  
  // Prepariamo gli argomenti extra
  const args = [
    "--quiz", quizPath,
    "--model", model,
    "--batch-size", String(batchSize),
    "--headless"
  ];
  if (withSearch) {
    args.push("--with-search");
  }
  
  const pythonInterpreter = "./venv/bin/python";
  
  let proc;
  try {
    // Spawna il processo Python in background pilotato in pipe
    proc = Bun.spawn([pythonInterpreter, `scripts/${scriptName}`, ...args], {
      stdout: "pipe",
      stderr: "pipe"
    });
  } catch (spawnErr) {
    console.clear();
    console.log(RED + "=".repeat(80));
    console.log(` ❌ IMPOSSIBILE AVVIARE LO SCRIPT: ${spawnErr}`);
    console.log("=".repeat(80) + RESET);
    console.log("\n Premere [Invio] per tornare al menu...");
    await waitReturn();
    return;
  }

  const stdoutNodeStream = Readable.fromWeb(proc.stdout as any);
  const stdoutReader = readline.createInterface({ input: stdoutNodeStream });
  
  // Raccoglitore asincrono degli errori (stderr) con inoltro real-time al log della TUI
  let pythonErrors = "";
  const stderrPromise = (async () => {
    try {
      const stderrNodeStream = Readable.fromWeb(proc.stderr as any);
      const stderrReader = readline.createInterface({ input: stderrNodeStream });
      for await (const line of stderrReader) {
        pythonErrors += line + "\n";
        if (line.trim()) {
          lastLog = `${RED}⚠️ [Stderr] ${line.trim()}${RESET}`;
          drawProgressTUI();
        }
      }
    } catch (err) {
      // Ignora errori di chiusura stream
    }
  })();

  // Variabili per il calcolo delle statistiche di visualizzazione
  let totalBatches = 0;
  let currentBatch = 0;
  let totalEnriched = 0;
  let totalFailed = 0;
  let lastLog = "Avvio arricchimento...";
  let isPaused = false;
  let startTime = Date.now();
  let elapsedSeconds = 0;

  // Renderizza la barra di avanzamento e le info
  function drawProgressTUI() {
    console.clear();
    console.log(CYAN + "=".repeat(80));
    console.log(" 🤖 ARRICCHIMENTO IN CORSO (TUI TS)");
    console.log("=".repeat(80) + RESET + "\n");
    console.log(`  • Quiz:       ${BOLD}${path.basename(quizPath)}${RESET}`);
    console.log(`  • Modello:    ${BOLD}${model}${RESET}`);
    console.log(`  • Stato:      ${isPaused ? RED + "IN PAUSA ⏸️" : GREEN + "IN ELABORAZIONE 🔄"}${RESET}`);
    console.log(DIM + "-".repeat(80) + RESET);

    // Barra di progresso
    const percent = totalBatches > 0 ? (currentBatch / totalBatches) * 100 : 0;
    const filled = Math.min(40, Math.floor(percent / 2.5));
    const bar = "█".repeat(filled) + "░".repeat(40 - filled);
    console.log(` PROGRESSO:`);
    console.log(` [${bar}] ${percent.toFixed(1)}% (Batch ${currentBatch}/${totalBatches})\n`);

    // Statistiche
    console.log(` STATISTICHE:`);
    console.log(`  • Domande arricchite in sessione:  ${totalEnriched}`);
    console.log(`  • Batch falliti:                    ${totalFailed}`);
    
    const minutes = Math.floor(elapsedSeconds / 60);
    const secs = elapsedSeconds % 60;
    const timeStr = `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    console.log(`  • Tempo trascorso:                  ${timeStr}`);

    if (currentBatch > 0 && elapsedSeconds > 0) {
      const speed = currentBatch / elapsedSeconds;
      const remainingBatches = totalBatches - currentBatch;
      const etaSecs = Math.round(remainingBatches / speed);
      const etaMin = Math.floor(etaSecs / 60);
      const etaSec = etaSecs % 60;
      console.log(`  • Tempo stimato (ETA):              ~${String(etaMin).padStart(2, "0")}:${String(etaSec).padStart(2, "0")}`);
    } else {
      console.log(`  • Tempo stimato (ETA):              --:--`);
    }

    console.log(DIM + "-".repeat(80) + RESET);
    console.log(` ULTIMO LOG:`);
    console.log(`  ${lastLog}`);
    console.log("\n" + CYAN + "=".repeat(80) + RESET);
    console.log(" COMANDI: [P] Pausa/Riprendi  |  [Q] Salva ed Esci in sicurezza");
  }

  // Timer per aggiornare il tempo trascorso a schermo
  const timer = setInterval(() => {
    if (!isPaused && !isRunning) {
      elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
      drawProgressTUI();
    }
  }, 1000);

  // Ascoltatore dei tasti per pausa (SIGSTOP/SIGCONT) ed interruzione (SIGINT)
  const keyHandler = (str: any, key: any) => {
    if (!key) return;

    if (key.name === "p") {
      if (!isPaused) {
        // Mette in pausa il processo figlio
        proc.kill("SIGSTOP");
        isPaused = true;
        lastLog = "Processo messo in pausa dall'utente.";
        drawProgressTUI();
      } else {
        // Riprende il processo figlio
        proc.kill("SIGCONT");
        isPaused = false;
        // Ripristiniamo la data di avvio per non calcolare il tempo di pausa nell'ETA
        startTime = Date.now() - (elapsedSeconds * 1000);
        lastLog = "Processo ripreso.";
        drawProgressTUI();
      }
    } else if (key.name === "q" || (key.ctrl && key.name === "c")) {
      // Ferma il processo inviando SIGINT per farlo salvare ed uscire in sicurezza
      proc.kill("SIGINT");
      lastLog = "Interruzione richiesta... salvataggio dei dati completati.";
      drawProgressTUI();
    }
  };

  process.stdin.on("keypress", keyHandler);

  // Ciclo principale di lettura output dello script headless
  try {
    for await (const line of stdoutReader) {
      try {
        const payload = JSON.parse(line.trim());
        if (payload.type === "start") {
          totalBatches = payload.total_batches;
          drawProgressTUI();
        } else if (payload.type === "progress") {
          currentBatch = payload.batch;
          totalEnriched = payload.enriched;
          totalFailed = payload.failed;
          lastLog = payload.log;
          drawProgressTUI();
        } else if (payload.type === "finish") {
          lastLog = `Completato! Arricchite ${payload.enriched} domande. Stato finale: ${payload.status}`;
          drawProgressTUI();
          break;
        }
      } catch {
        // Se non è JSON, lo consideriamo un log testuale generico dello script
        if (line.trim()) {
          lastLog = line.trim();
          drawProgressTUI();
        }
      }
    }
  } catch (err) {
    lastLog = `Errore di comunicazione col processo: ${err}`;
    drawProgressTUI();
  }

  // Pulisce l'ascoltatore e il timer
  clearInterval(timer);
  process.stdin.off("keypress", keyHandler);

  // Aspettiamo che il processo esca
  const code = await proc.exited;

  // Piccolo ritardo per consentire all'event loop di elaborare gli ultimi frammenti dello stream stderr
  await sleep(100);
  
  if (code !== 0) {
    console.log("\n" + RED + "=".repeat(80));
    console.log(" ❌ LO SCRIPT PYTHON E' TERMINATO IN CRASH");
    console.log("=".repeat(80) + RESET);
    if (pythonErrors.trim()) {
      console.log(RED + "\nDettagli dell'errore (Stderr):" + RESET);
      console.log(pythonErrors);
    }
  } else {
    console.log("\n" + CYAN + "=".repeat(80));
    console.log(" ✅ Esecuzione completata con successo!");
    console.log("=".repeat(80) + RESET);
  }

  console.log(` Codice uscita: ${code}`);
  console.log(" Premere [Invio] per tornare al menu...");
  console.log(CYAN + "=".repeat(80) + RESET);
  
  await waitReturn();
}

async function startEnrichmentFlow(scriptItem: ScriptItem) {
  const isOllama = scriptItem.script.includes("ollama");
  
  // 1. Selezione del Quiz
  const quizPath = await selectQuizInteractive();
  if (!quizPath) return;

  // 2. Selezione del Modello
  const model = await selectModelInteractive(isOllama);
  if (!model) return;

  // 3. Sottomenu opzioni
  let batchSize = 5;
  let withSearch = false;
  while (true) {
    console.clear();
    console.log(CYAN + "=".repeat(80));
    console.log(` ⚙️ OPZIONI ARRICCHIMENTO: ${scriptItem.name}`);
    console.log("=".repeat(80) + RESET + "\n");
    console.log(`  • Quiz selezionato:            ${BOLD}${path.basename(quizPath)}${RESET}`);
    console.log(`  • Modello LLM scelto:           ${BOLD}${model}${RESET}`);
    console.log(`  • Dimensione dei Batch:         ${BOLD}${batchSize}${RESET}`);
    console.log(`  • Ricerca Web su Incertezza:    ${withSearch ? GREEN + "SI (RAG attivo) 🔍" : RED + "NO"}${RESET}\n`);

    console.log(" OPERAZIONI DISPONIBILI:");
    console.log("  [1] Avvia Arricchimento");
    console.log("  [2] Esplora Statistiche e Dettagli Quiz");
    console.log("  [3] Modifica dimensione Batch");
    console.log("  [4] Attiva/Disattiva Ricerca Web su Incertezza");
    console.log("\n  [B] Indietro (Annulla)");
    console.log(CYAN + "=".repeat(80) + RESET);

    const choice = await readSingleChar();
    if (choice === "b") {
      break;
    } else if (choice === "1") {
      const relQuizPath = path.relative("quizzes", quizPath);
      await runEnrichmentHeadless(scriptItem.script, relQuizPath, model, batchSize, withSearch);
      break;
    } else if (choice === "2") {
      await exploreQuizTS(quizPath);
    } else if (choice === "3") {
      console.log(`\nDimensione batch corrente: ${batchSize}`);
      const val = await promptQuestion("Nuova dimensione: ");
      const parsed = parseInt(val);
      if (!isNaN(parsed) && parsed > 0) {
        batchSize = parsed;
      } else {
        console.log(`${RED}Valore non valido.${RESET}`);
        await sleep(1000);
      }
    } else if (choice === "4") {
      withSearch = !withSearch;
    }
  }
}

async function startGenerateQuizFlow() {
  const pdfPath = await selectPDFInteractive();
  if (!pdfPath) return;

  const model = await selectModelInteractive(false);
  if (!model) return;

  const relPathToQuizzes = path.relative("quizzes", pdfPath);
  await runScriptStandard(
    {
      name: "Generatore di Quiz da PDF",
      script: "generate_quiz.py",
      description: "",
      detailedDescription: ""
    },
    ["--pdf", relPathToQuizzes, "--model", model]
  );
}

// ============================================================================
// CORE TUI ED ESECUZIONE STANDARD SCRIPT PYTHON
// ============================================================================

function drawTUI() {
  console.clear();
  console.log(CYAN + "=".repeat(80));
  console.log("  🤖 UNI QUIZ GLOBAL TUI - RUNNER INTERATTIVO (Bun + TypeScript)");
  console.log("=".repeat(80) + RESET + "\n");

  console.log(" Seleziona lo script da eseguire usando le frecce [↑ / ↓]:\n");

  for (let i = 0; i < SCRIPTS.length; i++) {
    const isSelected = i === selectedIdx;
    const prefix = isSelected ? " ➔ \x1b[1;32m●" : "    \x1b[0;37m○";
    const suffix = isSelected ? RESET : "";
    const nameStr = `${prefix} ${SCRIPTS[i].name} (${SCRIPTS[i].script})${suffix}`;
    console.log(nameStr);
    console.log(`     ${DIM}${SCRIPTS[i].description}${RESET}`);
  }

  console.log("\n\x1b[1;36m" + "-".repeat(80) + RESET);
  const selected = SCRIPTS[selectedIdx];
  console.log(` ${YELLOW}DETTAGLIO SCRIPT SELEZIONATO:${RESET}`);
  console.log(`  • Nome:   ${selected.name}`);
  console.log(`  • File:   scripts/${selected.script}`);
  console.log(`  • Info:   ${selected.detailedDescription}`);
  console.log(CYAN + "=".repeat(80) + RESET);
  console.log(" COMANDI: [Invio] Avvia  |  [F] Avvia con argomenti  |  [Q / Esc] Esci");
}

async function runScriptStandard(item: ScriptItem, extraArgs: string[]) {
  isRunning = true;
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
  }

  // Intercettiamo lo script PDF parser che richiede parametri posizionali obbligatori
  if (item.script === "pds_quiz_pdf.py" && extraArgs.length === 0) {
    console.clear();
    console.log(YELLOW + "=".repeat(80));
    console.log(" 📝 RICHIESTA PARAMETRI SCRIPT PDF PARSER");
    console.log("=".repeat(80) + RESET + "\n");
    
    const pdfPath = await promptQuestion(" Inserisci il percorso del file PDF di input: ");
    if (!pdfPath.trim()) {
      console.log(`\n${RED}❌ Percorso PDF vuoto. Annullato.${RESET}`);
      await sleep(1500);
      isRunning = false;
      if (process.stdin.isTTY) {
        process.stdin.setRawMode(true);
      }
      drawTUI();
      return;
    }
    
    const outputPath = await promptQuestion(" Inserisci il percorso del file JSON di output: ");
    if (!outputPath.trim()) {
      console.log(`\n${RED}❌ Percorso JSON vuoto. Annullato.${RESET}`);
      await sleep(1500);
      isRunning = false;
      if (process.stdin.isTTY) {
        process.stdin.setRawMode(true);
      }
      drawTUI();
      return;
    }
    extraArgs = [pdfPath.trim(), outputPath.trim()];
  }

  console.clear();
  console.log(YELLOW + "=".repeat(80));
  console.log(` ESECUZIONE: ${item.name} (${item.script})`);
  if (extraArgs.length > 0) {
    console.log(` Argomenti:  ${extraArgs.join(" ")}`);
  }
  console.log("=".repeat(80) + RESET + "\n");

  const pythonInterpreter = "./venv/bin/python";

  try {
    const proc = Bun.spawn([pythonInterpreter, `scripts/${item.script}`, ...extraArgs], {
      stdout: "inherit",
      stdin: "inherit",
      stderr: "inherit"
    });

    const exitCode = await proc.exited;
    console.log("\n\x1b[1;36m" + "=".repeat(80));
    console.log(` Terminato con codice: ${exitCode}`);
    console.log(" Premere [Invio] per tornare al menu...");
    console.log("=".repeat(80) + RESET);

    if (process.stdin.isTTY) {
      process.stdin.setRawMode(true);
    }
    await waitReturn();
  } catch (err) {
    console.error(`\n❌ Errore durante l'esecuzione dello script:`, err);
    console.log("\nPremere [Invio] per tornare al menu...");
    if (process.stdin.isTTY) {
      process.stdin.setRawMode(true);
    }
    await waitReturn();
  }

  isRunning = false;
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(true);
  }
  drawTUI();
}

async function promptAndRunScript(item: ScriptItem) {
  // Ignoriamo la richiesta standard di parametri liberi se è il parser PDF, dato che ha già il suo prompt guidato
  if (item.script === "pds_quiz_pdf.py") {
    await runScriptStandard(item, []);
    return;
  }

  isRunning = true;
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
  }

  console.log(`\n\n\x1b[1;33m📝 Inserisci argomenti extra per ${item.script} (es. --plan-only):\x1b[0m`);
  const val = await promptQuestion("> ");
  const extraArgs = val.trim().split(/\s+/).filter(Boolean);
  await runScriptStandard(item, extraArgs);
}

// ============================================================================
// UTILITY PER TERM / INPUT (PROMISE BASED)
// ============================================================================

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function promptQuestion(query: string): Promise<string> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(query, (ans) => {
      rl.close();
      resolve(ans);
    });
  });
}

function waitReturn(): Promise<void> {
  return new Promise((resolve) => {
    const handler = (str: any, key: any) => {
      if (key && key.ctrl && key.name === "c") {
        console.clear();
        process.exit(0);
      }
      if (key && key.name === "return") {
        process.stdin.off("keypress", handler);
        resolve();
      }
    };
    process.stdin.on("keypress", handler);
  });
}

function readSingleChar(): Promise<string> {
  return new Promise((resolve) => {
    const handler = (str: any, key: any) => {
      if (key && key.ctrl && key.name === "c") {
        console.clear();
        process.exit(0);
      }
      if (key && key.name) {
        process.stdin.off("keypress", handler);
        resolve(key.name);
      } else if (str) {
        process.stdin.off("keypress", handler);
        resolve(str.toLowerCase());
      }
    };
    process.stdin.on("keypress", handler);
  });
}

function readKeyName(): Promise<string> {
  return new Promise((resolve) => {
    const handler = (str: any, key: any) => {
      if (key && key.ctrl && key.name === "c") {
        console.clear();
        process.exit(0);
      }
      if (key && key.name) {
        process.stdin.off("keypress", handler);
        resolve(key.name);
      }
    };
    process.stdin.on("keypress", handler);
  });
}

async function checkAndSetupEnvironment() {
  const venvPath = path.join(process.cwd(), "venv");

  // Se il venv esiste già, verifichiamo che le dipendenze siano importabili.
  // In questo modo, se viene aggiunto un nuovo requisito in requirements.txt (es. duckduckgo-search),
  // l'ambiente verrà aggiornato automaticamente.
  let depsOk = true;
  if (fs.existsSync(venvPath)) {
    try {
      const pythonInterpreter = "./venv/bin/python";
      const checkProc = Bun.spawn([
        pythonInterpreter,
        "-c",
        "import google.genai, requests, duckduckgo_search"
      ], {
        stdout: "ignore",
        stderr: "ignore"
      });
      const checkExit = await checkProc.exited;
      if (checkExit !== 0) {
        depsOk = false;
      }
    } catch {
      depsOk = false;
    }
  }

  if (!fs.existsSync(venvPath) || !depsOk) {
    console.clear();
    console.log(YELLOW + "=".repeat(80));
    console.log(fs.existsSync(venvPath)
      ? " ⚠️  AGGIORNAMENTO DIPENDENZE PYTHON RILEVATO"
      : " ⚠️  CONFIGURAZIONE AMBIENTE VIRTUALE PYTHON (venv)"
    );
    console.log("=".repeat(80) + RESET + "\n");
    if (!fs.existsSync(venvPath)) {
      console.log(" L'ambiente virtuale 'venv' non è stato rilevato nella root del progetto.");
    } else {
      console.log(" Alcune dipendenze richieste dagli script (es. duckduckgo-search) non risultano installate nel venv.");
    }
    console.log(" Posso configurare/aggiornare l'ambiente per te installando i requisiti da 'scripts/requirements.txt'.\n");

    const answer = await promptQuestion(" Desideri configurare/aggiornare l'ambiente venv adesso? [Y/n]: ");
    if (answer.toLowerCase() === "n" || answer.toLowerCase() === "no") {
      console.log(`\n${YELLOW}⚠️  Avvio in corso senza aggiornamenti. Gli script Python potrebbero fallire.${RESET}`);
      await sleep(2000);
      return;
    }

    if (!fs.existsSync(venvPath)) {
      console.log("\n🔧 1/2 Creazione dell'ambiente virtuale (python3 -m venv venv)...");
      try {
        const venvProc = Bun.spawn(["python3", "-m", "venv", "venv"], {
          stdout: "inherit",
          stderr: "inherit"
        });
        const venvExit = await venvProc.exited;
        if (venvExit !== 0) {
          throw new Error(`Errore durante la creazione del venv (codice ${venvExit})`);
        }
      } catch (err) {
        console.log(`\n${RED}❌ Errore durante la creazione del venv: ${err}${RESET}`);
        console.log(" Premere [Invio] per continuare comunque...");
        await waitReturn();
        return;
      }
    }

    console.log("\n📦 Installazione/Aggiornamento dei requisiti (venv/bin/pip install -r scripts/requirements.txt)...");
    try {
      const pipProc = Bun.spawn(["./venv/bin/pip", "install", "-r", "scripts/requirements.txt"], {
        stdout: "inherit",
        stderr: "inherit"
      });
      const pipExit = await pipProc.exited;
      if (pipExit !== 0) {
        throw new Error(`Errore durante l'installazione delle dipendenze (codice ${pipExit})`);
      }

      console.log(`\n${GREEN}✅ Ambiente configurato/aggiornato correttamente con successo!${RESET}`);
      await sleep(2000);
    } catch (err) {
      console.log(`\n${RED}❌ Errore durante l'installazione delle dipendenze: ${err}${RESET}`);
      console.log(" Premere [Invio] per continuare comunque...");
      await waitReturn();
    }
  }
}

// ============================================================================
// INITIALIZATION
// ============================================================================

readline.emitKeypressEvents(process.stdin);

const globalKeypressHandler = async (str: any, key: any) => {
  if (isRunning) return;

  // Intercettazione dell'uscita robusta (Ctrl+C, Q, Esc)
  if (
    str === "\u0003" ||
    str === "q" ||
    str === "Q" ||
    (key && (key.name === "escape" || key.name === "q" || (key.ctrl && key.name === "c")))
  ) {
    console.clear();
    process.exit(0);
  }

  if (key) {
    if (key.name === "up") {
      selectedIdx = (selectedIdx - 1 + SCRIPTS.length) % SCRIPTS.length;
      drawTUI();
    } else if (key.name === "down") {
      selectedIdx = (selectedIdx + 1) % SCRIPTS.length;
      drawTUI();
    } else if (key.name === "return") {
      const selected = SCRIPTS[selectedIdx];
      
      // Disattiva i tasti globali prima di entrare in flussi interattivi/sottoprocessi
      disableGlobalKeys();

      if (selected.script === "tui_explorer") {
        const quizPath = await selectQuizInteractive();
        if (quizPath) {
          await exploreQuizTS(quizPath);
        }
      } else if (selected.script === "generate_quiz.py") {
        await startGenerateQuizFlow();
      } else if (selected.script.includes("enrich")) {
        await startEnrichmentFlow(selected);
      } else {
        await runScriptStandard(selected, []);
      }

      // Riattiva i tasti globali e ridisegna il menu all'uscita
      enableGlobalKeys();
      drawTUI();
    } else if (key.name === "f") {
      disableGlobalKeys();
      await promptAndRunScript(SCRIPTS[selectedIdx]);
      enableGlobalKeys();
      drawTUI();
    }
  }
};

function enableGlobalKeys() {
  process.stdin.on("keypress", globalKeypressHandler);
}

function disableGlobalKeys() {
  process.stdin.off("keypress", globalKeypressHandler);
}

async function start() {
  if (process.stdin.isTTY) {
    process.stdin.setRawMode(false);
  }
  await checkAndSetupEnvironment();

  if (process.stdin.isTTY) {
    process.stdin.setRawMode(true);
  }
  enableGlobalKeys();
  drawTUI();
}

start();
