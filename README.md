# แนวทางการสร้างโปรเจค Final Exam — Local RAG for Programming

โฟลเดอร์นี้เป็น **โปรเจคตัวอย่างที่ทำงานได้ครบตามสัญญา (contract)** นักศึกษาใช้เป็นจุดเริ่มต้นแล้วปรับปรุงให้ได้คะแนนสูงขึ้นได้เลย

---

## 1. ภาพรวม

นักศึกษาสร้าง **HTTP service** หนึ่งตัวใน Docker image ซึ่งต้องทำได้ 3 อย่าง

| ความสามารถ | Endpoint | ใช้วัดอะไร |
|---|---|---|
| รับเอกสารความรู้ (knowledge) แล้วทำดัชนี | `POST /knowledge`, `DELETE /knowledge/{namespace}` | RAG pipeline |
| ตอบข้อสอบปรนัยโดยอ้างอิงความรู้ที่ส่งให้ | `POST /ask` | ความแม่นของการค้นคืน + การให้เหตุผล |
| เขียนโปรแกรม Python ตาม requirement | `POST /code` | การสร้างโค้ดที่รันผ่าน unit test |

ตอนประเมิน ระบบของผู้สอนจะดำเนินการตามลำดับนี้

1. build image จากงานที่ส่ง
2. รัน container บนเครือข่ายปิดที่**ไม่มีอินเทอร์เน็ต** เครือข่ายนี้มี Ollama กลางให้ใช้ และโหลดโมเดลไว้แล้ว
3. ส่ง knowledge ของ case study ที่ไม่เปิดเผยล่วงหน้า แล้วถามข้อสอบปรนัย
4. ขอให้เขียนโค้ด แล้วนำโค้ดที่ได้ไปรันกับ unit test ใน sandbox แยกต่างหาก

```
 ผู้สอน (harness) ──HTTP──▶  container ของนักศึกษา :8000 ──HTTP──▶  Ollama กลาง :11434
                              (โค้ดของนักศึกษา)                   (qwen2.5-coder, nomic-embed-text)
```

> สัญญาฉบับเต็มอยู่ที่ [`../spec/openapi.yaml`](../spec/openapi.yaml) (ดูได้จากพอร์ทัลที่ `/spec/openapi.yaml` ด้วย)

---

## 2. กติกาบังคับ (ถ้าไม่ทำตาม งานจะถูกปฏิเสธหรือได้ 0 คะแนน)

1. มี `Dockerfile` และ `manifest.json` อยู่ที่ **root** ของ repo หรือ zip
   - zip ที่มีโฟลเดอร์ครอบอยู่ชั้นเดียวก็ใช้ได้ ระบบจะแกะโฟลเดอร์นั้นออกให้
2. service ฟังที่ **port 8000** บน `0.0.0.0`
3. **ห้ามใส่ไฟล์โมเดล**ในงาน และห้ามดาวน์โหลดโมเดลตอน build หรือตอนรัน
   - นามสกุลที่ห้าม: `.gguf`, `.safetensors`, `.pt`, `.pth`, `.onnx`, `.ckpt`, `.h5`, `.tflite`
   - จำกัดไฟล์ละไม่เกิน 20MB และรวมไม่เกิน 200MB หลังแตก zip
4. ต้องอ่านค่าเหล่านี้จาก **environment variable** ห้ามเขียนค่าตายตัวในโค้ด

   | ตัวแปร | ค่าตอนประเมิน |
   |---|---|
   | `OLLAMA_HOST` | `http://grader-ollama:11434` |
   | `LLM_MODEL` | ค่า `llm_model` จาก `manifest.json` |
   | `EMBED_MODEL` | ค่า `embed_model` จาก `manifest.json` |

5. `manifest.json` ต้องมี `student_id` ตรงกับรหัสที่ใช้ส่ง และเลือกโมเดลจาก**รายการที่อนุญาต**เท่านั้น
   ```json
   {
     "student_id": "6612345678",
     "name": "ชื่อ นามสกุล",
     "llm_model": "qwen2.5-coder:7b",
     "embed_model": "nomic-embed-text",
     "notes": "อธิบายสั้น ๆ ว่าทำอะไรเพิ่ม (ไม่บังคับ)"
   }
   ```
   - โมเดลที่อนุญาตตอนนี้คือ `llm_model` = `qwen2.5-coder:7b` หรือ `qwen2.5-coder:14b` และ `embed_model` = `nomic-embed-text`
   - ผู้สอนจะประกาศถ้ามีการเปลี่ยนรายการ
6. container ตอนประเมินจะถูกจำกัดดังนี้ งานต้องทำงานได้ภายใต้เงื่อนไขเหล่านี้
   - **ไม่มีอินเทอร์เน็ต** ห้าม `pip install` หรือดาวน์โหลดอะไรตอนรัน ให้ติดตั้งทุกอย่างตอน build
   - root filesystem เป็น **read-only** เขียนได้เฉพาะ `/tmp` (1GB) และ `/data` (512MB)
   - ห้ามใช้ `/tmp` ร่วมกับ `/data` เป็นที่เก็บแบบถาวร เพราะข้อมูลหายเมื่อ container หยุด
   - RAM 4GB, 2 CPU, ไม่มี capability พิเศษ
7. `GET /health` ต้องตอบ `{"status":"ok"}` ภายใน **180 วินาที**หลัง container เริ่มทำงาน
8. ต้องตอบภายในเวลาที่กำหนด

   | endpoint | timeout |
   |---|---|
   | `/health` | 10 วินาที |
   | `/knowledge` | 600 วินาที |
   | `DELETE /knowledge` | 30 วินาที |
   | `/ask` | 90 วินาที |
   | `/code` | 180 วินาที |

9. ห้ามพยายามเข้าถึงสิ่งอื่นนอกจาก Ollama กลาง และห้ามโกงระบบ เช่น hard-code คำตอบ หรืออ่านไฟล์ของผู้สอน
   - ถ้าพบ จะได้ 0 คะแนนทั้งงาน

---

## 3. API Contract พร้อมตัวอย่าง

ทุก request และ response ใช้ JSON แบบ UTF-8 (ภาษาไทยส่งเป็นตัวอักษรตรง ๆ)

### 3.1 `GET /health`
```json
{"status": "ok", "student_id": "6612345678", "llm_model": "qwen2.5-coder:7b",
 "embed_model": "nomic-embed-text", "version": "1.0.0"}
```

### 3.2 `POST /knowledge` — รับเอกสารเข้าดัชนี
```json
{
  "namespace": "case11",
  "documents": [
    {"doc_id": "11_fenwick_tree", "content": "# Fenwick Tree\n...", "format": "markdown"}
  ]
}
```
ตอบกลับ:
```json
{"namespace": "case11", "documents": 1, "chunks": 42}
```
- `namespace` เป็นตัวอักษร `A-Z a-z 0-9 _ . -` ยาวไม่เกิน 64 ตัว แต่ละชุดข้อสอบใช้ namespace ของตัวเอง
- ถ้าส่ง `doc_id` เดิมซ้ำ ให้**แทนที่**ข้อมูลเดิม ห้ามเพิ่มซ้ำ
- `chunks` ต้องเป็นจำนวนเต็ม

### 3.3 `DELETE /knowledge/{namespace}`
```json
{"namespace": "case11", "deleted": true}
```
- namespace ที่ไม่มีอยู่ต้องตอบ 200 ได้ด้วย โดยให้ `deleted` เป็น `false`
- harness เรียก endpoint นี้ทั้งก่อนและหลังทดสอบแต่ละชุด

### 3.4 `POST /ask` — ตอบข้อสอบปรนัย
```json
{
  "namespace": "case11",
  "question_id": "case11-q01",
  "question": "Fenwick tree ใช้เวลาเท่าใดในการอัปเดตค่าหนึ่งตำแหน่ง",
  "options": [
    {"key": "ก", "text": "O(1)"},
    {"key": "ข", "text": "O(log n)"},
    {"key": "ค", "text": "O(n)"},
    {"key": "ง", "text": "O(n log n)"}
  ]
}
```
ตอบกลับ:
```json
{
  "question_id": "case11-q01",
  "answer": "ข",
  "sources": [{"doc_id": "11_fenwick_tree", "text": "...การอัปเดต ... O(log n)...", "score": 0.83}]
}
```
- `answer` ต้องเป็น **key ตัวใดตัวหนึ่งใน `options`** ถ้าตอบอย่างอื่น ข้อนั้นจะผิด
- ระบบสลับลำดับตัวเลือกทุกครั้ง จึงห้ามเดาจากตำแหน่ง
- `sources` เป็นข้อมูลประกอบ ไม่คิดคะแนน แต่ช่วยในการ debug

### 3.5 `POST /code` — เขียนโปรแกรม
```json
{
  "task_id": "case11-c01",
  "requirement": "เขียนฟังก์ชัน lowbit(i) คืนค่าบิตที่มีค่าน้อยที่สุดที่เป็น 1 ของ i ...",
  "language": "python",
  "entry_point": "lowbit",
  "signature": "def lowbit(i: int) -> int:",
  "namespace": "case11"
}
```
ตอบกลับ:
```json
{"task_id": "case11-c01", "language": "python", "code": "def lowbit(i: int) -> int:\n    return i & -i\n"}
```
- `code` ต้องเป็น Python ที่มีฟังก์ชันชื่อตาม `entry_point`
- จะห่อด้วย ```` ```python ```` หรือไม่ก็ได้
- harness จะ `exec` โค้ด แล้วเรียกฟังก์ชันด้วย test case ที่ซ่อนไว้
- `namespace` อาจเป็น `null` ซึ่งหมายถึงโจทย์ที่ไม่ต้องใช้ knowledge
- ถ้าไม่ใช่ `null` ให้ดึงความรู้จาก namespace นั้นมาช่วยได้ เช่น นิยามเฉพาะของ case study
- โค้ดจะรันใน sandbox ที่**ไม่มีเครือข่าย** และใช้ได้เฉพาะ Python standard library ห้าม `import numpy` และไลบรารีภายนอกอื่น
- แต่ละ test case มีเวลาจำกัด (ปกติไม่เกิน 5 วินาที)
- ห้ามพิมพ์ผลออก stdout แทนการ `return`

### 3.6 Error
- ถ้าเกิดข้อผิดพลาด ให้ตอบ HTTP 4xx หรือ 5xx พร้อม `{"detail": "..."}`
- harness นับข้อที่ error ว่าผิด แล้วทำข้อต่อไป ไม่หยุดทั้งชุด

---

## 4. โครงสร้างโปรเจคตัวอย่าง

```
exampleStu/
├── Dockerfile            # python:3.11-slim, user ไม่ใช่ root, port 8000
├── manifest.json         # ★ แก้ student_id / name / โมเดล
├── requirements.txt      # fastapi, uvicorn, httpx, numpy, pydantic (ล็อกเวอร์ชัน)
├── docker-compose.yml    # ใช้บนเครื่องตัวเอง (+ profile tunnel)
├── app/
│   ├── main.py           # endpoints ทั้งหมด + แยกคำตอบ/โค้ดจากข้อความของ LLM
│   ├── config.py         # อ่าน manifest.json + env (OLLAMA_HOST, LLM_MODEL, TOP_K, ...)
│   ├── ollama_client.py  # เรียก Ollama /api/embed และ /api/chat
│   ├── rag.py            # ตัด chunk ตามหัวข้อ markdown + เก็บ vector + cosine search
│   ├── prompts.py        # system/user prompt ของ MC และ code
│   └── schemas.py        # pydantic models ตามสัญญา
└── tools/
    ├── selfcheck.py      # ★ ตรวจสัญญา + คิดคะแนนตัวอย่างบนเครื่องตัวเอง
    └── sample_pack/      # ชุดข้อสอบตัวอย่าง (เหมือนชุด practice บนพอร์ทัล)
```

pipeline ของตัวอย่างทำงานดังนี้

- `/knowledge` ตัด markdown ตามหัวข้อ (`#`) แล้วใช้หน้าต่างประมาณ 900 ตัวอักษร ซ้อนกัน 150 ตัวอักษร
- จากนั้น embed ด้วย `nomic-embed-text` โดยเติม prefix `search_document:` แล้วเก็บไว้ในหน่วยความจำ
- `/ask` embed คำถามพร้อมตัวเลือก (prefix `search_query:`) แล้วเลือก top-5 chunks
- จากนั้นให้ LLM ตอบเป็น JSON `{"reason": ..., "answer": ...}` (temperature 0)
- ถ้า JSON เสีย จะใช้ regex แทน และถ้ายังไม่ได้ จะ fallback เป็นตัวเลือกแรก
- `/code` ใส่ requirement, signature และ context (ถ้ามี) ลงใน prompt แล้วดึงโค้ดจากคำตอบ
- ถ้าได้ `SyntaxError` จะขอให้ LLM แก้อีก 1 รอบ

---

## 5. รันบนเครื่องตัวเอง

### 5.1 เตรียม Ollama (ทำครั้งเดียว)
ติดตั้งจาก <https://ollama.com/download> แล้วรัน
```bash
ollama pull qwen2.5-coder:7b
```
```bash
ollama pull nomic-embed-text
```
qwen2.5-coder:7b ต้องใช้ RAM หรือ VRAM ประมาณ 6GB ถ้าเครื่องไม่พอ ให้พัฒนาด้วยโมเดลเล็กไปก่อน เช่น `qwen2.5-coder:1.5b` โดยตั้ง env `LLM_MODEL=qwen2.5-coder:1.5b` แต่ใน `manifest.json` ต้องระบุโมเดลที่อนุญาต

### 5.2 แบบไม่ใช้ Docker (เร็วที่สุดตอนพัฒนา)
```bash
python -m venv .venv
```
```bash
.venv\Scripts\activate
```
(macOS/Linux: `source .venv/bin/activate`)
```bash
pip install -r requirements.txt
```
```bash
uvicorn app.main:app --port 8000 --reload
```
ค่าเริ่มต้นของ `OLLAMA_HOST` คือ `http://localhost:11434`

### 5.3 แบบ Docker (ต้องผ่านแบบนี้ก่อนส่ง เพราะผู้สอนประเมินแบบนี้)
```bash
docker compose up --build
```
- container จะเรียก Ollama บนเครื่องผ่าน `host.docker.internal`
- บน Linux ถ้า Ollama ฟังแค่ `127.0.0.1` ให้ตั้ง `OLLAMA_HOST=0.0.0.0` ให้ Ollama ก่อน
- ถ้าขึ้น `port is already allocated` ให้ใช้พอร์ตอื่นบนเครื่อง เช่น `APP_PORT=8001` (PowerShell: `$env:APP_PORT="8001"`) แล้วรัน selfcheck ด้วย `--url http://localhost:8001` (ภายใน container ยังเป็น 8000 ตามกติกา)
- `docker-compose.yml` ตั้ง `read_only: true` ไว้เหมือนตอนประเมิน ถ้าโค้ดพยายามเขียนไฟล์นอก `/tmp` จะเห็นปัญหาตั้งแต่ตอนนี้

---

## 6. ตรวจงานก่อนส่ง

### 6.1 Self-check บนเครื่อง
```bash
python tools/selfcheck.py
```
ใช้ได้ทั้งตอนรันตามข้อ 5.2 และ 5.3 โดยสคริปต์จะทำสิ่งเหล่านี้

- ตรวจรูปแบบ response ทุก endpoint
- คิดคะแนนข้อปรนัยตัวอย่าง
- รัน unit test ของโจทย์โค้ดตัวอย่างกับโค้ดที่ service สร้าง

ถ้าขึ้น `Contract checks passed.` แปลว่ารูปแบบถูกต้อง ส่วนคะแนนในชุดตัวอย่างเป็นเพียงแนวโน้ม ข้อสอบจริงเป็นคนละชุด

ตัวอย่างผลของโปรเจคนี้ (qwen2.5-coder:7b): MC 5/6 และโค้ด 3 ข้อผ่าน 7/7, 7/8, 4/10 test

### 6.2 ทดสอบออนไลน์ผ่านพอร์ทัล (Cloudflare quick tunnel)
ใช้ตรวจว่าเครื่องผู้สอนเรียก service ของเราผ่านอินเทอร์เน็ตได้จริง

1. เปิด service ตามข้อ 5.2 หรือ 5.3 ไว้
2. เปิด tunnel ด้วยวิธีใดวิธีหนึ่ง
   - Docker:
     ```bash
     docker compose --profile tunnel up --build
     ```
     แล้วดู URL ใน log ของ `tunnel` ซึ่งจะมีบรรทัด `https://xxxx-xxxx.trycloudflare.com`
   - ติดตั้ง [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) แล้วรัน
     ```bash
     cloudflared tunnel --url http://localhost:8000
     ```
3. ไปที่พอร์ทัลของวิชา แล้วเลือกเมนู **ทดสอบออนไลน์** จากนั้นเข้าสู่ระบบ (ดูข้อ 8) และใส่ URL `https://….trycloudflare.com`
4. ไปที่เมนู **ตรวจสถานะ** เพื่อดูผล ได้แก่ health, จำนวน chunk, คะแนนปรนัยชุด practice และผลตรวจ syntax ของโค้ด
   - การทดสอบออนไลน์**ไม่รันโค้ด** ให้ใช้ selfcheck บนเครื่องเพื่อรัน unit test
   - กดทดสอบซ้ำได้ทุก 5 นาที
   - ผลการทดสอบออนไลน์**ไม่นับคะแนน** คะแนนจริงมาจากการประเมินงานที่ส่งในเครื่องของผู้สอน

> URL ของ quick tunnel เปลี่ยนทุกครั้งที่เปิดใหม่ และใช้ได้เฉพาะตอนที่เครื่องเราเปิดอยู่

---

## 7. แนวทางปรับปรุงเพื่อเพิ่มคะแนน

ส่วนที่ได้ผลมากที่สุดมักเป็นการค้นคืน (retrieval)

- **Chunking**: แยกตามหัวข้อย่อย และเก็บชื่อหัวข้อแม่ไว้ใน chunk ด้วย ระวังอย่าตัดตาราง, code block หรือ list กลางคัน แล้วลองปรับ `CHUNK_SIZE` และ `CHUNK_OVERLAP`
- **Query**: ค้นแยกด้วยคำถามและแต่ละตัวเลือก แล้วรวมผล หรือทำ query expansion
- **Hybrid search**: รวม BM25 หรือ keyword match เข้ากับ vector search ข้อนี้ช่วยมากกับชื่อเฉพาะและตัวเลข เขียนเองด้วย Python ล้วนได้
- **Re-ranking**: ให้ LLM ให้คะแนน chunk ที่ค้นได้ก่อนนำไปตอบ แต่ต้องระวังเวลา เพราะ `/ask` มีเวลา 90 วินาที
- **Prompt สำหรับข้อปรนัย**: สั่งให้ยึดเอกสารเป็นหลักเมื่อขัดกับความรู้ทั่วไป เพราะ case study บางเรื่องเป็นข้อมูลสมมุติ และระวังคำปฏิเสธ เช่น "ข้อใด**ไม่**ถูกต้อง"
- **Self-consistency**: ถามหลายครั้งแล้วโหวต (temperature > 0) ทำได้ถ้าเวลาพอ
- **โค้ด**: ใส่ตัวอย่าง input/output จาก requirement ลงใน prompt และสั่งให้ใช้ standard library เท่านั้น
  - ให้ service ทดสอบโค้ดกับตัวอย่างใน requirement เองก่อนตอบ ถ้าผิดให้แก้ (loop ไม่เกิน 1–2 รอบ)
  - ระวังการรันโค้ดของ LLM ภายใน container ของตัวเอง ให้ใช้ `subprocess` พร้อม timeout
- **โมเดล 14b**: ฉลาดกว่า แต่ช้ากว่ามาก ทดสอบเวลาให้ดีก่อนเลือก
- **ความทนทาน**: ทุก endpoint ต้องไม่ล่ม ถ้า LLM ตอบแปลก ให้ fallback ไปเป็นคำตอบที่ถูกรูปแบบเสมอ

ทุกครั้งที่ปรับ ให้วัดผลด้วย `selfcheck.py` และลองสร้างชุดข้อสอบของตัวเองเพิ่ม โดยใช้รูปแบบเดียวกับ `tools/sample_pack/` แล้วรันด้วย `--pack`

---

## 8. การส่งงาน

### 8.1 เข้าสู่ระบบ
พอร์ทัลอาจเปิดให้ใช้วิธีใดวิธีหนึ่งหรือทั้งสองวิธี แล้วแต่ที่ผู้สอนตั้งไว้

- **เข้าสู่ระบบด้วย Google (Gmail)**
  1. กด **เข้าสู่ระบบ** แล้วเลือกบัญชี Google
  2. ครั้งแรกระบบจะให้กรอก **รหัสนักศึกษาและชื่อ** เพื่อผูกกับอีเมลนั้น การผูกนี้ทำได้ครั้งเดียว ถ้ากรอกผิดต้องให้ผู้สอนยกเลิกให้
  3. ครั้งต่อไปเข้าสู่ระบบด้วยอีเมลเดิมได้เลย ไม่ต้องกรอกรหัสอีก
  - รหัสที่ลงทะเบียนต้องตรงกับ `student_id` ใน `manifest.json`
- **รหัสส่งงาน**: กรอกรหัสนักศึกษาและรหัสส่งงานที่ได้รับจากผู้สอน

### 8.2 ส่งงาน
เลือกเมนู **ส่งงาน** แล้วเลือกวิธีส่งวิธีใดวิธีหนึ่ง

| วิธี | รายละเอียด |
|---|---|
| **GitHub** (แนะนำ) | ใส่ URL รูปแบบ `https://github.com/<user>/<repo>` (ระบุ branch หรือ tag ได้)<br>ระบบจะบันทึก **commit SHA ณ เวลาที่ส่ง** commit ที่ push หลังจากนั้นจะไม่ถูกใช้จนกว่าจะส่งใหม่<br>ถ้า repo เป็น private ต้องเพิ่มบัญชีของผู้สอนเป็น collaborator ก่อน |
| **Zip** | ไม่เกิน 50MB ต้องไม่มี `.venv/`, `__pycache__/`, `.git/` หรือไฟล์โมเดล |

- ระบบจะ**ตรวจโครงสร้างทันที** เช่น มี Dockerfile หรือไม่, manifest ถูกต้องหรือไม่, มีไฟล์ต้องห้ามหรือไม่ ถ้าไม่ผ่านจะแสดงรายการที่ต้องแก้ทันที
- ส่งซ้ำได้ไม่จำกัดจนถึงกำหนดส่ง ระบบใช้**ครั้งล่าสุดที่ผ่านการตรวจ**
- การตรวจตอนส่งไม่ได้ build image ดังนั้นต้องทดสอบ `docker compose up --build` ให้ผ่านบนเครื่องตัวเองก่อนส่ง

### Checklist ก่อนส่ง
- [ ] แก้ `manifest.json` ให้ `student_id` และ `name` เป็นของตัวเอง และโมเดลอยู่ในรายการที่อนุญาต
- [ ] `docker compose up --build` แล้ว `python tools/selfcheck.py` ขึ้น `Contract checks passed.`
- [ ] ไม่มีไฟล์โมเดล, `.env`, `.venv` หรือข้อมูลส่วนตัวในงาน
- [ ] ไม่ต้องใช้อินเทอร์เน็ตตอนรัน (ติดตั้ง dependency ทั้งหมดใน `Dockerfile`)
- [ ] (แนะนำ) ทดสอบออนไลน์ผ่านพอร์ทัลแล้วได้ผล health = ok

---

## 9. คำถามที่พบบ่อย

**ใช้ภาษาหรือ framework อื่นได้ไหม**
ได้ ถ้า Dockerfile build ได้และ API ตรงตามสัญญา แต่ฝั่ง `/code` ต้องตอบเป็น**โค้ด Python** เสมอ

**ใช้ vector DB เช่น Chroma หรือ FAISS ได้ไหม**
ได้ ถ้าติดตั้งใน image และเก็บข้อมูลใน `/tmp` หรือ `/data` แต่ระวังขนาด image และเวลาเริ่มต้น เพราะต้อง healthy ภายใน 180 วินาที

**ใช้ LangChain หรือ LlamaIndex ได้ไหม**
ได้ แต่ต้องตั้งให้เรียก Ollama ผ่าน `OLLAMA_HOST` และห้ามมีส่วนใดเรียกอินเทอร์เน็ต เช่น การดาวน์โหลด tokenizer จาก HuggingFace ตอนรัน

**ใช้ OpenAI หรือ Claude API ได้ไหม**
ไม่ได้ ตอนประเมินไม่มีอินเทอร์เน็ต ใช้ได้เฉพาะ Ollama กลางที่มีโมเดลตามรายการที่อนุญาตเท่านั้น

**เก็บ knowledge ข้ามการรีสตาร์ทต้องทำไหม**
ไม่ต้อง ในการประเมินหนึ่งรอบ harness จะส่ง `/knowledge` ใหม่ก่อนถามทุกครั้ง

**`/ask` ตอบช้ามากในครั้งแรก**
ครั้งแรกต้องโหลดโมเดลเข้าหน่วยความจำ (ตัวอย่างนี้ใช้ประมาณ 50 วินาทีบนเครื่องทดสอบ) เครื่องประเมินจะ warm-up โมเดลให้ก่อน แต่ควรทำให้แต่ละคำถามเร็วพอเผื่อไว้

**ลงทะเบียนแล้วขึ้นว่า "รหัสนักศึกษานี้ถูกลงทะเบียนด้วยอีเมลอื่นแล้ว"**
แปลว่ามีอีเมลอื่นผูกรหัสนี้ไปก่อน ให้แจ้งผู้สอนทันที ผู้สอนยกเลิกการผูกได้ แล้วคุณค่อยลงทะเบียนใหม่

**ได้ `answer is not an option key`**
แปลว่าตอบสิ่งที่ไม่ใช่ key เช่น `"ข."` หรือ `"O(log n)"` ต้อง map ให้เหลือแค่ `"ข"` ดูตัวอย่างได้ที่ `parse_answer()` ใน `app/main.py`
