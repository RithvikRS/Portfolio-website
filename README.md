# Rithvik’s portfolio

A responsive professional portfolio for full-stack, cloud, and machine learning engineering roles. Built with semantic HTML, custom CSS, and vanilla JavaScript. The pages are static; an optional Node server uses Nodemailer to deliver contact messages through your SMTP provider. No external fonts or build service required.

## Preview and check

With Node.js 22.9 or later and pnpm installed, run these commands from this directory:

```sh
pnpm install --frozen-lockfile --ignore-scripts
node scripts/build.mjs
node scripts/check.mjs
node --test tests/*.test.mjs
node --env-file-if-exists=.env server/index.mjs
```

Open **http://127.0.0.1:4173**. Stop the server with Ctrl+C. Equivalent pnpm commands are `pnpm build`, `pnpm check`, `pnpm test`, and `pnpm dev`. Build and content checks still run without installing dependencies; running the server requires Nodemailer. The old `node scripts/serve.mjs` preview command also works, but does not automatically load `.env`.

Copy `.env.example` to `.env` and fill in your SMTP provider settings to enable delivery locally. Do not commit this file. Without SMTP configuration, the dialog offers LinkedIn and disables submission. Tests use fake delivery functions and never send real email. Change both `PORT` and `PUBLIC_ORIGIN` if using a different preview port. The form must be tested through HTTP/HTTPS, not by opening an HTML file directly.

## Update the content

- Edit `data/portfolio.json` for roles, descriptions, projects, skills, credentials, education, and contact details, including the Credly profile URL.
- Each project separates `technologies` (confirmed languages, libraries, and tools) from `skills` (the technical approaches demonstrated). Leave `technologies` empty when the description does not identify a stack. Do not infer a project's tools from the general CV skills.
- The toolkit displays skills as plain text tags. Project cards retain their own applied skills and confirmed tools.
- `professionalAwards` and `awards` appear together in one Honors & recognition section, with general honors first, followed by Accenture awards. Optional `scope`, `date`, `description`, and `image` fields supply labels and details; missing details are omitted. Homepage recognition links lead to this shared collection.
- Replace `documents/Rithvik_CV.pdf` to update every CV download. That alone does not change the text on the pages; update the content file for changes to roles or other details.
- Run `node scripts/build.mjs` after content or template edits. It regenerates `index.html`, `Projects.html`, `Awards.html`, `404.html`, `error.html`, and `sitemap.xml`.
- Run `node scripts/check.mjs` to validate local links, anchors, document structure, and the PDF download.
- Commit the generated pages alongside the content and the current CV. Generated HTML should not be edited directly.

## Files and behavior

- `scripts/build.mjs`: shared HTML templates and page generation.
- `css/site.css`: colors, type, component styles, responsive layout, print styles, and reduced-motion support.
- `js/site.js`: mobile navigation, project filters/search, linked project expansion, accessible contact dialog, active navigation, and scroll entrance animations.
- A roughly 1.5-second introduction brings in the brand and navigation, reveals the homepage headline line by line, then introduces the description, buttons, and illustration with a brief connector animation. Inner-page introductions use the same staggered rhythm. This plays on page loads at the top; anchor links and restored scroll positions skip it. Links remain usable throughout. Sections start revealing just before entering the viewport, with small sibling delays and no nested tag animations. The illustration uses one frame scheduler with time-based easing for pointer tilt and gentle scroll movement; it stops when settled or offscreen. Hover effects and dialogs use consistent easing. There is no automatic scrolling or continuously running decorative loop. The footer's motion toggle is remembered locally; OS reduced-motion preferences always take priority. Keyboard focus and printing cancel entrance animations. Content is never hidden by animation-specific CSS.
- `server/`: public-file allowlist, same-origin contact API, validation, rate limits, duplicate-submission protection, and SMTP delivery. Recipient and credentials remain in server configuration. Visitor addresses are used for Reply-To only.
- `deploy/`: Caddy/systemd templates and the Oracle VM setup guide.
- `images/favicon.svg`: local vector identity. The hero illustration and project diagrams use inline SVG/CSS.
- The existing `Projects.html` and `Awards.html` URLs are retained, as are the original main-page anchors. `error.html` remains available; `404.html` supplies the GitHub Pages error page.
- Content, navigation, downloads, and project overviews work without JavaScript. JavaScript adds search, filtering, a collapsible mobile menu, and the contact form. LinkedIn remains the contact fallback without JavaScript.

## Hosting

For Docker, follow the [container deployment guide](deploy/DOCKER.md). `docker compose up --build -d --wait` starts a local preview at `http://localhost:8080`; the separate production Compose file adds Caddy HTTPS for an Oracle VM. The image build regenerates and validates the site, and SMTP credentials are supplied only at runtime.

The generated pages still work with GitHub Pages served directly from the repository root, but GitHub Pages cannot run the SMTP backend. To enable email delivery on a Linux VM, follow [the Oracle deployment guide](deploy/README.md). It includes HTTPS, service startup, provider configuration, and delivery verification. No VM or email provider has been configured by this rebuild.

If the public URL changes, update `siteUrl` in the content file and rebuild to refresh canonical URLs, sitemap, and the 404 page base URL. The supplied Node/Caddy setup serves at the domain root.

The public pages use a form and LinkedIn instead of displaying a destination email or phone number. The CV is unchanged and may contain contact details. Removing visible contact details does not remove them from downloaded PDFs, public source, old commits, or copies indexed elsewhere. Review those separately if you want a public CV with fewer contact details.

This rebuild does not publish or push automatically. The previous Bootstrap and jQuery setup is no longer loaded; the old Bootstrap files and source images remain in the repository for reference.

## Content sources

- `documents/Rithvik_CV.pdf` is the primary source for current professional experience, skills, certification issue dates, and education.
- Publicly accessible LinkedIn information was reviewed at <https://www.linkedin.com/in/rithvikrs/>. Full profile and recent activity access was limited.
- Earlier project descriptions, academic awards, and additional coursework were retained from the original site. They are labeled as earlier work, with no invented client projects, performance metrics, credential validity dates, or repository links.
- The exact portfolio repository URL comes from this checkout’s Git remote. Other project-specific repository links can be added using a project’s optional `url` field once confirmed.
- Project links and selected tool mappings were also checked against the public GitHub repository descriptions: OpenCV/TensorFlow for mask detection; OpenCV, Hough transforms, and DNN object detection for the lane project; HTML/CSS/PHP for hospital management; and C++ for library management. Other tools are limited to the original descriptions and this portfolio’s implementation. Individual project codebases have not been audited.
- Credly links open the user-provided public profile. Certification dates remain sourced from the CV; no badge status, expiry date, or additional certification was inferred from the profile link.
- Accenture's company-level Pinnacle and ACE awards, and project-level Quarterly and Star awards, were supplied directly by the user. The user described more than three years on the current project. The approximate 2025–2026 dates for Pinnacle and ACE remain unconfirmed and are omitted publicly; counts, selection criteria, and business impact have not been inferred.

Certification dates are issue dates recorded in the CV, not a claim of current credential validity. Review role dates and wording whenever the CV changes.
