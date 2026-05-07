# feed-mixer

Fetch a bunch of RSS/Atom feeds listed in an OPML file, mix their recent
entries together, and write a single combined Atom feed. Designed to run on a
schedule via GitHub Actions and publish the result to GitHub Pages.

## What it does

- Parses an OPML file for `xmlUrl` entries.
- Fetches every feed concurrently (with size, timeout, and content-length
  guards).
- Filters entries by age (`MIN_FEED_ENTRY_AGE_HOURS` ..
  `MAX_FEED_ENTRY_AGE_DAYS`).
- Copies entry summary or content as-is — no extraction, stripping, or
  truncation.
- Caches feed responses on disk so transient fetch failures don't drop a feed
  from the output.
- Writes a single Atom file to `OUTPUT_FILE`.

## Quick start

1. **Fork** this repo.
2. Replace [`feeds.opml`](feeds.opml) with your own OPML list of feeds.
3. Edit [`src/config.py`](src/config.py) — at minimum set `FEED_TITLE`,
   `FEED_SUBTITLE`, `FEED_AUTHOR`, `FEED_URL`, and `FEED_HOME_URL`.
4. [Set up the GitHub Action](#setting-up-the-github-action).
5. [Set up GitHub Pages](#setting-up-github-pages).
6. Push your changes. The Action runs hourly and republishes the feed.

## Setting up the GitHub Action

The workflow at [`.github/workflows/update.yml`](.github/workflows/update.yml)
runs hourly, on every push to `main`, and on manual dispatch. It needs
permission to push to a `gh-pages` branch.

1. In your fork, go to **Settings → Actions → General**.
2. Under **Workflow permissions**, select **Read and write permissions** and
   click **Save**. This lets the workflow create and update the `gh-pages`
   branch.
3. Go to the **Actions** tab. If Actions are disabled on your fork, click
   **I understand my workflows, go ahead and enable them**.
4. Open the **feed-mixer** workflow and click **Enable workflow** to enable it.
5. Next, click **Run workflow** to trigger the
   first build manually (the schedule will take over after that).
5. Wait for the run to finish. It will create a `gh-pages` branch containing
   your generated Atom file.

## Setting up GitHub Pages

After the first successful Action run has created the `gh-pages` branch:

1. Go to **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **Deploy from a branch**.
3. Set **Branch** to `gh-pages` and the folder to `/ (root)`. Click **Save**.
4. Wait a minute, then refresh the Pages settings page. GitHub will show the
   public URL, e.g. `https://<you>.github.io/<repo>/`.
5. Your mixed feed is served at
   `https://<you>.github.io/<repo>/<basename of OUTPUT_FILE>` — for example
   `https://<you>.github.io/<repo>/mixed.atom` with the default config.
6. Update `FEED_URL` in [`src/config.py`](src/config.py) to that public URL
   and push, so the Atom file's self-link points at the right place.

If you use a custom domain, add a `CNAME` file to the repo root containing
your domain (the workflow copies it into `_site/` so it lands at the root of
the `gh-pages` branch), and configure the domain under
**Settings → Pages → Custom domain**. Without the `CNAME` file in the
published branch, GitHub clears the custom-domain setting on every deploy.

## Local usage

Requires Python 3.10 or newer.

```sh
make setup                     # one time: create venv, install deps
make run                       # fetch and build
make run CACHE_FALLBACK=true   # fall back to cached feeds on fetch failure
make clean                     # remove generated atom file
```

You can also invoke the script directly:

```sh
python src/mixer.py --cache-fallback --verbose
```

## Configuration

All knobs live in [`src/config.py`](src/config.py):

| Setting | Purpose |
| --- | --- |
| `FEED_TITLE`, `FEED_SUBTITLE`, `FEED_AUTHOR` | Metadata for the generated feed |
| `FEED_URL`, `FEED_HOME_URL` | Public URLs of the generated feed and its home page |
| `OPML_FILE` | Path to your OPML file |
| `OUTPUT_FILE` | Where to write the mixed Atom feed (must be under `_site/` to be published) |
| `MIN_FEED_ENTRY_AGE_HOURS` | Skip entries newer than this (de-flake) |
| `MAX_FEED_ENTRY_AGE_DAYS` | Drop entries older than this |
| `MAX_FEED_ENTRIES` | Cap entries pulled from each source feed |
| `MAX_WORKERS` | Concurrent fetchers |
| `REQUEST_TIMEOUT`, `MAX_CONTENT_LENGTH`, `UA` | HTTP fetch limits |
| `CACHE_DIR` | Where to cache fetched feed bodies |

## License

See [LICENSE](LICENSE).
