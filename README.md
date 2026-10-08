# Rithvik’s portfolio

A responsive professional portfolio for full-stack, cloud, and machine learning engineering roles. The public pages use generated HTML, custom CSS, and vanilla JavaScript. A Node server serves the site, delivers contact messages through Nodemailer, and renders a protected admin dashboard. Production runs on Oracle with Docker Compose, Caddy HTTPS, and Authelia authentication. No external fonts or hosted build service are required.

## Current deployment

Deployment record updated **8 October 2026 (Asia/Kolkata)**. The Oracle checkout is `/opt/portfolio`, on `main`, at `144.24.135.201`. No-IP supplies the hostname; Caddy supplies HTTPS and routes requests to the containers.

| Resource | Address | Status |
| --- | --- | --- |
| Public portfolio | [rithvik.ddns.net](https://rithvik.ddns.net/) | Live, with SMTP configured |
| Admin dashboard | [/admin/](https://rithvik.ddns.net/admin/) | Stage 1 deployed; login required |
| Shared sign-in | [/auth/](https://rithvik.ddns.net/auth/) | Authelia, username/password |
| Portainer | [/portainer/](https://rithvik.ddns.net/portainer/) | Stage 2 deployed; shared login |
| Blog and learning notebook | No live route yet | Stage 3, awaiting separate approval |

The dashboard links to the portfolio and Portainer. Portainer CE 2.45.2 uses Authelia OpenID Connect for the existing administrator account and manages the Oracle Docker environment. Blog and learning-note editing remain pending separate approval.

The stage 1 deployment passed 15 automated tests, live HTTPS sign-in/sign-out and access checks, and desktop/mobile layout review. The contact API reported delivery available; these checks did not send email. This is a deployment record, not a continuously monitored status page.

After an outage and reboot on 8 October, the public site and complete dashboard/Portainer SSO flow were verified again. Saved logs showed repeated host memory exhaustion in `dnf-makecache.service`. Its background cache timer is now disabled on Oracle; package updates remain available. See the [incident and recovery record](deploy/DOCKER.md#8-october-2026-memory-exhaustion-and-recovery).

## Documentation

- [Docker and Oracle operation](deploy/DOCKER.md): which file to use, local preview, first deployment, redeployment, and Caddy routing.
- [Admin dashboard and shared login](deploy/ADMIN.md): account access, password recovery, persistent data, backups, and troubleshooting.
- [Portainer and SSO](deploy/PORTAINER.md): container management, recovery access, storage, and the stage 2 integration.
- [Alternative host deployment](deploy/README.md): Node and Caddy with systemd, plus contact behavior and limits.
- [Docker and Caddy PDF guide](output/pdf/Portfolio%20Docker%20and%20Caddy%20Guide.pdf): a printable guide to the completed setup.

For the current Oracle deployment, commit the development changes, merge into `main`, and push. Then run this **inside the Oracle SSH session**:

```sh
bash /opt/portfolio_redeploy.sh
```

The shortcut already exists. It runs the repository's `portfolio_redeploy.sh`, builds and checks the app, applies production configuration, reconciles Portainer SSO, and verifies HTTPS. No new script needs to be pasted into the terminal. Authelia restarts during redeployment, so sign in again afterward. Stage 1 and 2 files were copied to Oracle before merging into `main`; merge the matching files before a normal redeployment. The script stops if server copies differ from the pushed versions.

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

This local command previews the public portfolio and contact API. It does not start Caddy or Authelia; `/admin/` remains closed by default. Use the production setup for the complete sign-in flow.

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
- `server/`: public-file allowlist, protected dashboard, same-origin contact API, validation, rate limits, duplicate-submission protection, and SMTP delivery. Recipient and credentials remain in server configuration. Visitor addresses are used for Reply-To only.
- `server/admin.mjs` and `css/admin.css`: dashboard markup, administrator identity checks, and responsive styling.
- `Dockerfile`: builds and tests the Node application image; Compose decides how to run it.
- `compose.yaml`, `compose.ip.yaml`, and `compose.production.yaml`: separate local, temporary public-IP, and production configurations. Use one at a time for a deployment.
- `portfolio_redeploy.sh`: pulls `main`, validates configuration, builds the app, starts services, and checks the public endpoints.
- `scripts/setup-admin.py`: one-time Linux administrator setup. It generates private account files and refuses to replace an existing `.auth/` directory.
- `scripts/setup-portainer.py`: prepares private Portainer/OIDC files without replacing existing credentials, then applies SSO settings and checks Docker access during redeployment.
- `deploy/Caddyfile.docker` and `deploy/authelia/configuration.yml`: production routing and non-secret authentication settings.
- `deploy/Caddyfile` and `deploy/portfolio.service`: alternative host-based templates, not the active Docker deployment.
- `images/favicon.svg`: local vector identity. The hero illustration and project diagrams use inline SVG/CSS.
- The existing `Projects.html` and `Awards.html` URLs are retained, as are the original main-page anchors. `error.html` remains available; `404.html` supplies the GitHub Pages error page.
- Content, navigation, downloads, and project overviews work without JavaScript. JavaScript adds search, filtering, a collapsible mobile menu, and the contact form. LinkedIn remains the contact fallback without JavaScript.

## Hosting

For Docker, follow the [container deployment guide](deploy/DOCKER.md). `docker compose up --build -d --wait` starts a local preview at `http://localhost:8080`; the separate production Compose file runs the app, Caddy, Authelia, and Portainer on Oracle. The image build regenerates and validates the site. SMTP credentials are supplied only at runtime. Private authentication and Portainer data live in `.auth/` and `.portainer/`.

The generated pages still work with GitHub Pages served directly from the repository root. GitHub Pages cannot run the contact backend, admin dashboard, or Authelia. The current Oracle deployment already runs these services. The [host-based guide](deploy/README.md) is an alternative for the public site and SMTP backend; it does not install shared login.

For Docker production, change `DOMAIN` in the server's `.env.production` and redeploy when moving to a new domain. Compose derives the public origin, build URL, and authentication URLs from it. For static or direct Node hosting, update `siteUrl` in the content file and rebuild. See [domain changes](deploy/DOCKER.md#changing-the-domain) for details.

The public pages use a form and LinkedIn instead of displaying a destination email or phone number. The CV is unchanged and may contain contact details. Removing visible contact details does not remove them from downloaded PDFs, public source, old commits, or copies indexed elsewhere. Review those separately if you want a public CV with fewer contact details.

Deployments are triggered manually; there is no automatic deployment on a Git push. Keep `.env`, `.env.production`, `.auth/`, `.portainer/`, passwords, and SSH keys out of Git. The previous Bootstrap and jQuery setup is no longer loaded; the old Bootstrap files and source images remain in the repository for reference.

## Content sources

- `documents/Rithvik_CV.pdf` is the primary source for current professional experience, skills, certification issue dates, and education.
- Publicly accessible LinkedIn information was reviewed at <https://www.linkedin.com/in/rithvikrs/>. Full profile and recent activity access was limited.
- Earlier project descriptions, academic awards, and additional coursework were retained from the original site. They are labeled as earlier work, with no invented client projects, performance metrics, credential validity dates, or repository links.
- The exact portfolio repository URL comes from this checkout’s Git remote. Other project-specific repository links can be added using a project’s optional `url` field once confirmed.
- Project links and selected tool mappings were also checked against the public GitHub repository descriptions: OpenCV/TensorFlow for mask detection; OpenCV, Hough transforms, and DNN object detection for the lane project; HTML/CSS/PHP for hospital management; and C++ for library management. Other tools are limited to the original descriptions and this portfolio’s implementation. Individual project codebases have not been audited.
- Credly links open the user-provided public profile. Certification dates remain sourced from the CV; no badge status, expiry date, or additional certification was inferred from the profile link.
- Accenture's company-level Pinnacle and ACE awards, and project-level Quarterly and Star awards, were supplied directly by the user. The user described more than three years on the current project. The approximate 2025–2026 dates for Pinnacle and ACE remain unconfirmed and are omitted publicly; counts, selection criteria, and business impact have not been inferred.

Certification dates are issue dates recorded in the CV, not a claim of current credential validity. Review role dates and wording whenever the CV changes.
