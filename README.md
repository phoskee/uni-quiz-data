# uni-quiz-data 🎓

Questo repository nasce con l'obiettivo di raccogliere, archiviare e standardizzare i quiz universitari. L'idea è quella di creare una base di dati strutturata in formato JSON, utile per facilitare lo studio e permettere l'integrazione di questi dati in applicazioni o piattaforme di apprendimento.

## 📂 Struttura del repository

Il progetto è organizzato nelle seguenti cartelle:

- `quizzes/`: Contiene i quiz già pronti e formattati. La struttura segue la gerarchia: `università / corso / materia`.
- `_docs/`: È lo spazio dedicato al materiale grezzo. Qui si possono caricare dispense, appunti o PDF che devono ancora essere convertiti in quiz. Questa cartella serve sia come archivio per chi vuole contribuire con i propri documenti, sia come fonte per chi vuole generare nuovi quiz.
- `scripts/`: Contiene gli strumenti di utilità, tra cui lo script per verificare che i file JSON siano scritti correttamente.

## 🤖 Come generare un quiz

Per trasformare i documenti presenti in `_docs/` in quiz strutturati, si consiglia l'uso di modelli di linguaggio (LLM).

### Uso di NotebookLM (Consigliato)
[NotebookLM](https://notebooklm.google.com/) è uno strumento particolarmente efficace perché permette di caricare i propri documenti come fonti e interrogarli per estrarre informazioni precise.

**Procedura consigliata:**
1. Carica i file di riferimento nel notebook.
2. Utilizza il prompt riportato di seguito per chiedere la generazione del quiz.
3. Verifica che il risultato sia un JSON valido e salvalo nella cartella corretta all'interno di `quizzes/`.

### Prompt per la generazione
Che si utilizzi NotebookLM o un'altra LLM (come ChatGPT o Claude), si può usare questo prompt per ottenere un risultato coerente con lo standard del progetto:

> "Analizza il documento e genera un set di domande a scelta multipla. Il risultato deve essere esclusivamente un array JSON di oggetti, dove ogni oggetto segue questa struttura:
> {
>   \"question\": \"Testo della domanda\",
>   \"options\": [
>     {\"text\": \"Opzione 1\", \"image\": \"\"},
>     {\"text\": \"Opzione 2\", \"image\": \"\"}
>   ],
>   \"correctIndex\": 0,
>   \"image\": \"\",
>   \"code\": \"\",
>   \"explanation\": \"Spiegazione del perché la risposta è corretta\",
>   \"hint\": \"Suggerimento per aiutare a rispondere\"
> }
> Assicurati che 'correctIndex' corrisponda all'indice corretto della risposta nell'array delle opzioni."

## ✅ Verifica della correttezza

Ogni file deve rispettare lo standard del progetto per essere utilizzato correttamente. 

È disponibile uno script Python che controlla automaticamente la struttura e segnala eventuali errori. Questo controllo viene eseguito **automaticamente** da GitHub Actions su ogni Pull Request: se i file non sono validi, la PR non potrà essere unita.

Per eseguire la verifica localmente prima di caricare le modifiche:
```bash
python3 scripts/validate.py
```

## 🚀 Come contribuire

Il contributo di chiunque è utile per ampliare il database. Il processo si articola in questi passaggi:
1. Caricare il materiale di studio in `_docs/`.
2. Generare il file JSON seguendo le indicazioni fornite nella sezione precedente.
3. Verificare il file con lo script di validazione.
4. Inviare una Pull Request con il nuovo quiz inserito nella cartella corrispondente.

---
*L'obiettivo è rendere il materiale didattico più accessibile e organizzato attraverso la condivisione.*
