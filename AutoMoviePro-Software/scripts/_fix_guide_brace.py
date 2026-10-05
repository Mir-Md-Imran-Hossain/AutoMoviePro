from pathlib import Path
p = Path(r"e:\All Project\AutoMovieProSAAS\AutoMoviePro-Website\guide.html")
t = p.read_text(encoding="utf-8")
needle = 'font-size:0.88rem">\n  "email":'
repl = 'font-size:0.88rem">{\n  "email":'
if needle in t:
    p.write_text(t.replace(needle, repl, 1), encoding="utf-8")
    print("fixed")
else:
    print("not found")
