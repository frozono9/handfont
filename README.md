# handfont

<img width="1512" height="761" alt="Screenshot 2026-03-23 at 16 29 15" src="https://github.com/user-attachments/assets/45a58082-56af-4771-9d12-60c195d5fe20" />

A local web app that generates fill-in PDF template sheets, then processes
your scanned/photographed handwriting into a complete font family (TTF, OTF, WOFF2).

## Quickstart

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the app
bash start.sh
# or: python3 app.py

# 3. Open in browser
open http://localhost:5000
```

## Workflow

### Step 1 — Generate your template PDF
- Go to **Generate Sheet**
- Enter your font name
- Select character sets (Basic A–Z, numbers, punctuation, extended/accented)
- Click **Download PDF Template**

### Step 2 — Fill in every character
- Open the PDF on your iPad (Files app → Markup, or any drawing app)
- Write each character in its cell using your own handwriting
- Use the blue baseline as a writing guide
- Keep size, weight, and slant consistent across all characters
- Export the completed pages as JPEG or PNG images (one per page)

### Step 3 — Upload and build your font
- Go to **Build Font**
- Upload your completed page images (in page order)
- Click **Build Font**
- Download the ZIP containing:
  - `YourFont.ttf`  — for desktop (Windows, macOS, Linux)
  - `YourFont.otf`  — alternative desktop format
  - `YourFont.woff2` — for web use

## How the font extraction works

1. Each uploaded image is deskewed and binarized using adaptive thresholding
   (handles uneven lighting from iPad screenshots)
2. Grid lines are detected to locate each cell
3. The handwritten glyph inside each cell is extracted and tight-cropped
4. Contours are traced and scaled to font units (1000 UPM)
5. fontTools assembles a valid OpenType font with proper metrics tables

## Character sets

| Set | Count | Notes |
|-----|-------|-------|
| A–Z uppercase | 26 | |
| a–z lowercase | 26 | |
| 0–9 numbers | 10 | |
| Punctuation & symbols | ~50 | .,;:!? etc. |
| Special | ~18 | © ® € £ etc. |
| Extended/accented | ~130 | À Ç Ñ ü ÿ etc. |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/generate-sheet` | Generate template PDF |
| POST | `/api/build-font` | Process scans → font ZIP |
| GET | `/api/char-map` | JSON list of all characters |

## Tips for best results

- **Scan resolution**: 300 DPI minimum; iPad retina screenshots work great
- **Lighting**: Even, diffuse lighting; avoid shadows across the page
- **Pen choice**: Fine-tipped stylus or 0.5mm pen for clean edges
- **Consistency**: The more uniform your letter forms, the better the font looks
- **Upload order**: Name your files 01.jpg, 02.jpg etc. so they sort correctly
