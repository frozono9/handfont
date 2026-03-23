"""
HandFont Web App — Flask Backend
"""
from flask import Flask, request, jsonify, send_file, render_template
from flask import after_this_request
from flask_cors import CORS
import os, io, json, zipfile, tempfile, uuid
from pathlib import Path

from generate_sheets import build_pdf
from build_font import process_scan, SHEET_CHAR_ORDER

app = Flask(__name__, template_folder='templates')
CORS(app) # Enable CORS for GitHub Pages
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

UPLOAD_DIR = Path(tempfile.gettempdir()) / "handfont_uploads"
OUTPUT_DIR = Path(tempfile.gettempdir()) / "handfont_output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/generate-sheet', methods=['POST'])
def generate_sheet():
    """Generate a PDF template sheet and return it."""
    data = request.json or {}
    font_name   = data.get('fontName', 'My Font')
    include_ext = data.get('extendedChars', True)
    include_punc= data.get('punctuation', True)

    tmp_path = OUTPUT_DIR / f"template_{uuid.uuid4().hex}.pdf"
    build_pdf(str(tmp_path), font_name=font_name,
              include_extended=include_ext, include_punctuation=include_punc)

    @after_this_request
    def cleanup(response):
        try: tmp_path.unlink()
        except: pass
        return response

    return send_file(str(tmp_path), mimetype='application/pdf',
                     as_attachment=True,
                     download_name=f"{font_name.replace(' ','_')}_template.pdf")


@app.route('/api/build-font', methods=['POST'])
def build_font_endpoint():
    """Accept uploaded scanned pages, return a ZIP of font files."""
    font_name = request.form.get('fontName', 'My Font')
    files = request.files.getlist('pages')

    if not files:
        return jsonify({'error': 'No pages uploaded'}), 400

    session_id = uuid.uuid4().hex
    upload_session = UPLOAD_DIR / session_id
    output_session = OUTPUT_DIR / session_id
    upload_session.mkdir()
    output_session.mkdir()

    saved_paths = []
    for i, f in enumerate(files):
        ext = Path(f.filename).suffix or '.jpg'
        save_path = upload_session / f"page_{i:03d}{ext}"
        f.save(str(save_path))
        saved_paths.append(str(save_path))

    try:
        font_files = process_scan(saved_paths, font_name=font_name,
                                  output_dir=str(output_session),
                                  char_order=SHEET_CHAR_ORDER)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    # Zip everything up
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in font_files:
            if os.path.exists(fp):
                zf.write(fp, Path(fp).name)
    zip_buf.seek(0)

    # Cleanup
    import shutil
    shutil.rmtree(str(upload_session), ignore_errors=True)
    shutil.rmtree(str(output_session), ignore_errors=True)

    safe = font_name.replace(' ', '_')
    return send_file(zip_buf, mimetype='application/zip',
                     as_attachment=True,
                     download_name=f"{safe}_fonts.zip")


@app.route('/api/build-font-direct', methods=['POST'])
def build_font_direct():
    """Accept uploaded scanned pages, return the TTF file URL and character list."""
    font_name = request.form.get('fontName', 'My Font')
    letter_spacing = float(request.form.get('letterSpacing', 1.0))
    scale_factor = float(request.form.get('scaleFactor', 1.0))
    baseline_shift = float(request.form.get('baselineShift', 0.0))
    
    overrides_json = request.form.get('overrides', '{}')
    overrides = {}
    try:
        data = json.loads(overrides_json)
        # data is now like { 'a': { 'scale': 1.2, 'offset': 0.1 } }
        for k, v in data.items():
            if isinstance(v, dict):
                # Ensure we have both values, default to global if missing or 1.0/0.0
                scale = float(v.get('scale', 1.0))
                offset = float(v.get('offset', 0.0))
                overrides[k] = (scale, offset)
            else:
                overrides[k] = (1.0, float(v))
    except:
        pass
    
    files = request.files.getlist('pages')
    if not files: return jsonify({'error': 'No pages'}), 400
    
    session_id = uuid.uuid4().hex
    upload_session = UPLOAD_DIR / session_id
    # We serve from static for the direct preview if possible, or just a temp path
    output_session = OUTPUT_DIR / session_id
    upload_session.mkdir(parents=True, exist_ok=True)
    output_session.mkdir(parents=True, exist_ok=True)
    
    saved_paths = []
    for i, f in enumerate(files):
        ext = Path(f.filename).suffix or '.jpg'
        save_path = upload_session / f"page_{i:03d}{ext}"
        f.save(str(save_path))
        saved_paths.append(str(save_path))
    
    try:
        # Crucial: extract glyphs ONCE and store them in the session
        # For simplicity in this demo, we'll re-scan if they aren't provided,
        # but a production app would cache the 'glyph_images' (the extracted images)
        # to avoid repeating the heavy OpenCV work during tuning.
        
        # We need to return the actual characters found
        font_files, extracted_chars = process_scan(saved_paths, font_name=font_name,
                                  output_dir=str(output_session),
                                  char_order=SHEET_CHAR_ORDER,
                                  letter_spacing=letter_spacing,
                                  scale_factor=scale_factor,
                                  baseline_shift=baseline_shift,
                                  overrides=overrides)
        
        ttf_path = [f for f in font_files if f.endswith('.ttf')][0]
        ttf_filename = os.path.basename(ttf_path)
        
        return jsonify({
            'ttf_url': f'/api/download-font/{session_id}/{ttf_filename}',
            'characters': extracted_chars
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-font/<session_id>/<filename>')
def download_font_temp(session_id, filename):
    # Retrieve the custom name if provided (sent via query param ?n=...)
    custom_name = request.args.get('n')
    if custom_name:
        import re
        safe = re.sub(r'[^a-zA-Z0-9]', '_', custom_name).lower()
        if not safe: safe = "handfont"
        return send_file(OUTPUT_DIR / session_id / filename, 
                         as_attachment=True, 
                         download_name=f"{safe}.ttf")
    return send_file(OUTPUT_DIR / session_id / filename)


@app.route('/api/char-map', methods=['GET'])
def char_map():
    """Return the character-to-position mapping for the sheets."""
    result = []
    page, row, col = 1, 0, 0
    for i, ch in enumerate(SHEET_CHAR_ORDER):
        result.append({
            'char': ch,
            'unicode': f'U+{ord(ch):04X}',
            'index': i,
            'page': page,
            'row': row,
            'col': col,
        })
        col += 1
        if col >= 10:
            col = 0
            row += 1
    return jsonify(result)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
