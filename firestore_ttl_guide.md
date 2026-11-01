# Guida alla Configurazione della Policy TTL (Time-To-Live) su Google Cloud Firestore

Per soddisfare il requisito di **cancellazione automatica di emergenza (fallback) a 5 giorni** per i messaggi mai recapitati (ad esempio se il client del destinatario rimane offline per 5 o più giorni), Google Cloud Firestore offre una funzionalità nativa ad alte prestazioni: **Firestore TTL Policies**.

I documenti inviati dall'applicazione includono già il campo `ttl_date` calcolato con la formula:
```python
ttl_date = datetime.datetime.utcnow() + datetime.timedelta(days=5)
```

Segui uno dei due metodi seguenti per abilitare il TTL:

---

## Metodo 1: Tramite Google Cloud Console (Interfaccia Web)

1. Accedi alla [Google Cloud Console](https://console.cloud.google.com/).
2. Seleziona il progetto Firebase associato alla tua applicazione.
3. Nel menu di navigazione a sinistra, vai su **Firestore** > **Time-to-live (TTL)** (oppure vai nella sezione **Indici** > scheda **TTL**).
4. Clicca su **Crea criterio TTL** (o **Create TTL Policy**).
5. Configura i parametri:
   - **ID Gruppo di raccolte (Collection group)**: `messages`
   - **Percorso del campo timestamp (Timestamp field path)**: `ttl_date`
6. Clicca su **Crea**.
7. *(Opzionale ma raccomandato)* Ripeti la procedura per la collection `chat_requests`:
   - **ID Gruppo di raccolte**: `chat_requests`
   - **Percorso del campo timestamp**: `ttl_date`

> **Nota di funzionamento**: Una volta impostata la policy, Firestore esamina periodicamente i documenti ed elimina automaticamente quelli in cui il valore del campo `ttl_date` è inferiore al timestamp corrente. Il processo è gestito internamente da Google Cloud a costo zero di compute per il tuo client.

---

## Metodo 2: Tramite Google Cloud SDK (`gcloud CLI`)

Se preferisci la riga di comando o l'automazione CI/CD:

1. Installa ed effettua il login su `gcloud`:
   ```bash
   gcloud auth login
   gcloud config set project IL_TUO_PROJECT_ID_FIREBASE
   ```

2. Abilita la policy TTL sulla raccolta `messages`:
   ```bash
   gcloud firestore fields ttls update ttl_date --collection-group=messages --enable-ttl
   ```

3. Abilita la policy TTL anche per `chat_requests`:
   ```bash
   gcloud firestore fields ttls update ttl_date --collection-group=chat_requests --enable-ttl
   ```

4. Per verificare lo stato della policy TTL:
   ```bash
   gcloud firestore fields ttls describe ttl_date --collection-group=messages
   ```
   Lo stato passerà a `ACTIVE`.

---

## Riepilogo Architetturale

| Canale di Cancellazione | Attore | Tempistica | Scopo |
|-------------------------|--------|------------|-------|
| **Primario: Acknowledge & Delete** | Client Destinatario Windows | Immediata (pochi millisecondi dopo il download) | Privacy assoluta: nessun messaggio risiede nel cloud |
| **Secondario: Firestore TTL** | Engine Google Cloud | 5 Giorni (`ttl_date`) | Pulizia automatica dei messaggi abbandonati se il destinatario è offline permanente |
