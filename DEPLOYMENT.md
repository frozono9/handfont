# Deploying to GitHub Pages

To run this site on GitHub Pages, we need to handle the Python backend separately, as GitHub Pages only hosts static files (HTML/JS/CSS).

## Option 1: Hybrid Deployment (Recommended for now)
1. **Frontend**: The `index.html` at the root of the repository is served by GitHub Pages.
2. **Backend**: Deploy the Python app to a service like [Render](https://render.com/), [Railway](https://railway.app/), or [Heroku](https://www.heroku.com/).
3. **Connect**: Update the `fetch()` URL in `index.html` to point to your deployed backend URL.

## Option 2: Full Client-Side (Future)
To make this work 100% on GitHub Pages without a server, the image processing (OpenCV) and font building (fontTools) must be rewritten in JavaScript using:
- **OpenCV.js**: For image binarization and cell detection.
- **opentype.js**: For generating the TTF file directly in the browser.

## Current Setup
I have copied `templates/index.html` to the root `index.html` so GitHub Pages can see it. 
Currently, it is configured to look for the backend at a placeholder URL.
