"""Build the single-file Tejas AI web app (published as a Claude artifact).

python web-app/build.py  ->  web-app/dist/tejas-ai-web.html
"""
import base64
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "tejas_ai" / "web"
OUT = Path(__file__).resolve().parent / "dist" / "tejas-ai-web.html"


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> None:
    html = (WEB / "index.html").read_text("utf-8")
    css = (WEB / "styles.css").read_text("utf-8")
    css = css.replace("url(fonts/Geist.woff2)", "url(" + data_uri(WEB / "fonts/Geist.woff2", "font/woff2") + ")")
    css = css.replace("url(fonts/Michroma.woff2)", "url(" + data_uri(WEB / "fonts/Michroma.woff2", "font/woff2") + ")")
    mark = data_uri(WEB / "icons/mark.png", "image/png")
    app = (WEB / "app.js").read_text("utf-8").replace('"icons/mark.png"', f'"{mark}"')
    live = (Path(__file__).parent / "live.js").read_text("utf-8")

    head = html[html.index("<head>") + 6: html.index("</head>")]
    body = html[html.index("<body") : html.rindex("</body>")]
    body = body[body.index(">") + 1:]
    body_attrs = re.search(r"<body([^>]*)>", html).group(1)

    # Keep title + theme meta; drop manifest, icons and the external stylesheet.
    keep = [ln for ln in head.splitlines() if re.search(r"<title>|theme-color", ln)]
    body = body.replace('src="icons/mark.png"', f'src="{mark}"')
    body = re.sub(r'<script src="app.js"></script>', "", body)
    web_css = (
        ":root{color-scheme:dark}"
        "#btnConnect,#btnConnect2{display:none!important}"
    )
    page = (
        "\n".join(keep) + "\n"
        + f"<style>{css}\n{web_css}</style>\n"
        + (f'<div{body_attrs}>' if body_attrs.strip() else "")
        + body
        + ("</div>" if body_attrs.strip() else "")
        + f"\n<script>{live}</script>\n<script>{app}</script>\n"
    )
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, "utf-8")
    print(f"{OUT} {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
