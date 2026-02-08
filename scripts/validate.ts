import { readFileSync, readdirSync } from "fs";
import { join } from "path";

const schemaPath = join(import.meta.dir, "schema.json");
const schema = JSON.parse(readFileSync(schemaPath, "utf-8"));

function validateQuiz(filePath: string) {
  console.log(`🔍 Validazione di: ${filePath}...`);
  try {
    const data = JSON.parse(readFileSync(filePath, "utf-8"));

    if (!Array.isArray(data)) {
      throw new Error("Il file deve contenere un array di domande.");
    }

    data.forEach((q, index) => {
      const errors: string[] = [];

      // Controllo campi obbligatori e tipi
      const requiredFields = ["question", "options", "correctIndex", "image", "code", "explanation", "hint"];
      requiredFields.forEach(field => {
        if (!(field in q)) errors.push(`Campo mancante: ${field}`);
      });

      if (typeof q.question !== "string") errors.push("question deve essere una stringa");
      if (typeof q.correctIndex !== "number") errors.push("correctIndex deve essere un numero");
      if (!Array.isArray(q.options) || q.options.length < 2) errors.push("options deve essere un array con almeno 2 risposte");
      
      if (q.options) {
        q.options.forEach((opt: any, optIdx: number) => {
          if (typeof opt.text !== "string") errors.push(`opzione ${optIdx} testo non valido`);
          if (typeof opt.image !== "string") errors.push(`opzione ${optIdx} immagine non valida`);
        });
      }

      if (q.correctIndex < 0 || (q.options && q.correctIndex >= q.options.length)) {
        errors.push(`correctIndex (${q.correctIndex}) fuori range per ${q.options?.length} opzioni`);
      }

      if (errors.length > 0) {
        console.error(`❌ Errore alla domanda #${index}:`);
        errors.forEach(err => console.error(`   - ${err}`));
        process.exit(1);
      }
    });

    console.log("✅ Validazione completata con successo!");
  } catch (err: any) {
    console.error(`❌ Errore critico nel file: ${err.message}`);
    process.exit(1);
  }
}

const target = process.argv[2];
if (!target) {
  console.log("Uso: bun validate.ts <file-o-cartella>");
  process.exit(1);
}

validateQuiz(target);
