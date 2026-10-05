# Rithvik’s portfolio

A responsive professional portfolio for full-stack, cloud, and machine learning engineering roles. Built with semantic HTML, custom CSS, and vanilla JavaScript. No production dependencies, external fonts, or build service required.

## Preview and check

With Node.js 18 or later installed, run these commands from this directory:

```sh
node scripts/build.mjs
node scripts/check.mjs
node scripts/serve.mjs
```

Open **http://127.0.0.1:4173**. Stop the server with Ctrl+C. Set `PORT` to use another port. Equivalent npm commands are `npm run build`, `npm run check`, and `npm run dev`; no `npm install` is needed.

## Update the content

- Edit `data/portfolio.json` for roles, descriptions, projects, skills, credentials, education, and contact details.
- Replace `documents/Rithvik_CV.pdf` to update every CV download. That alone does not change the text on the pages; update the content file for changes to roles or other details.
- Run `node scripts/build.mjs` after content or template edits. It regenerates `index.html`, `Projects.html`, `Awards.html`, `404.html`, `error.html`, and `sitemap.xml`.
- Run `node scripts/check.mjs` to validate local links, anchors, document structure, and the PDF download.
- Commit the generated pages alongside the content and the current CV. Generated HTML should not be edited directly.

## Files and behavior

- `scripts/build.mjs`: shared HTML templates and page generation.
- `css/site.css`: colors, type, component styles, responsive layout, print styles, and reduced-motion support.
- `js/site.js`: mobile navigation, project filters/search, linked project expansion, copy email, and active navigation.
- `images/favicon.svg`: local vector identity. The hero illustration and project diagrams use inline SVG/CSS.
- The existing `Projects.html` and `Awards.html` URLs are retained, as are the original main-page anchors. `error.html` remains available; `404.html` supplies the GitHub Pages error page.
- Content, navigation, downloads, and project overviews work without JavaScript. JavaScript adds search, filtering, and a collapsible mobile menu.

## Hosting

The generated pages work with GitHub Pages served directly from the repository root. Keep the existing hosting settings; no framework migration is needed. If the public URL changes, update `siteUrl` in the content file and rebuild to refresh canonical URLs, sitemap, and the 404 page base URL.

This rebuild does not publish or push automatically. The previous Bootstrap and jQuery setup is no longer loaded; the old Bootstrap files and source images remain in the repository for reference.

## Content sources

- `documents/Rithvik_CV.pdf` is the primary source for current professional experience, skills, certification issue dates, and education.
- Publicly accessible LinkedIn information was reviewed at <https://www.linkedin.com/in/rithvikrs/>. Full profile and recent activity access was limited.
- Earlier project descriptions, academic awards, and additional coursework were retained from the original site. They are labeled as earlier work, with no invented client projects, performance metrics, credential validity dates, or repository links.
- The exact portfolio repository URL comes from this checkout’s Git remote. Other project-specific repository links can be added using a project’s optional `url` field once confirmed.

Certification dates are issue dates recorded in the CV, not a claim of current credential validity. Review role dates and wording whenever the CV changes.
