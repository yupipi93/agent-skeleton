#!/usr/bin/env python3
"""Flag the tells that make a draft read machine-written, before it is sent.

Checks a Markdown or plain-text draft (English and Spanish) against the catalogue in
kit/bundles/style/skills/human-writing/references/ai-writing-tells.md, which follows
Wikipedia's "Signs of AI writing" guide:

  kit/bundles/style/scripts/ai-tells.py draft.md
  printf '%s' "$text" | kit/bundles/style/scripts/ai-tells.py --lang es

Levels:
  HARD  never acceptable in a deliverable: chatbot artifacts, placeholders, the em dash
        (U+2014), knowledge-cutoff lines, sycophantic openers
  WARN  a tell to rewrite: puffery, negative parallelism, participle tails, weasel
        attribution, didactic disclaimers, AI-vocabulary density, list and heading style
  NOTE  information only (a few AI-vocabulary words, below the density threshold)

Fenced code blocks, inline code and quoted lines (`>`) are skipped, except for the
artifact scan, which reads everything.

Options:
  --lang en|es|all   word lists to apply (default all)

Exit codes: 0 clean or notes only, 1 warnings, 2 at least one HARD finding, 64 usage.
Read-only, Python 3.8+, stdlib only.
"""
import argparse
import re
import statistics
import sys

I = re.IGNORECASE
APOS = "['’]"
# Start of a sentence: line start or after terminal punctuation.
SOS = r"(?:^|(?<=[.!?:])\s+)"

ARTIFACTS = [
    ("ChatGPT citation marker", r"contentReference|oaicite|oai_citation|turn\d+search\d+|attributableIndex"),
    ("Gemini citation marker", r"\[cite:\s?\d+\]|start_span|end_span"),
    ("Grok citation marker", r"grok_card|grok_render_citation"),
    ("DeepSeek citation marker", "【[^】]*†"),
    ("Perplexity citation marker", r"\[attached_file:\d+\]|\[web:\d+\]|ppl-ai-file-upload"),
    ("chatbot block marker", r":::writing"),
    ("chatbot link tracker", r"utm_source=(?:openai|chatgpt|copilot)|referrer=grok"),
    ("copied footnote return arrow", "↩"),
]

PLACEHOLDERS = [
    ("bracket placeholder", r"\[(?:your|insert|describe|add|enter|tu|tus|insertar|inserta|añadir|añade|nombre)\b[^\]\n]*\]", I),
    ("INSERT_ placeholder", r"\bINSERT_[A-Z0-9_]+\b", 0),
    ("placeholder date", r"\b(?:19|20)\d\d-[xX]{2}-[xX]{2}\b", 0),
    ("parenthesised placeholder", r"\((?:add|insert|put|añade|inserta|pon) [^)\n]{0,60}(?:here|aquí)\)", I),
]

# (category, label, regex, level, languages)
PHRASES = [
    # Machine-only lines.
    ("chatbot", "knowledge-cutoff disclaimer", r"\bas of my last (?:knowledge|training) (?:update|cutoff)\b|\bup to my last training\b", "HARD", "en"),
    ("chatbot", "self-reference as an AI", r"\bas an AI(?: language model)?\b", "HARD", "en"),
    ("chatbot", "sycophantic opener", SOS + r"(?:certainly|of course|absolutely|great question)!", "HARD", "en"),
    ("chatbot", "sycophantic opener", r"\byou" + APOS + r"re absolutely right\b", "HARD", "en"),
    ("chatbot", "sycophantic opener", SOS + "¡(?:claro|por supuesto|excelente pregunta|buena pregunta)", "HARD", "es"),
    ("chatbot", "cut-off marker", r"\bcontinue generating\b", "HARD", "en"),
    # Talking to the reader.
    ("chatter", "closing offer", r"\b(?:let me know if|feel free to|would you like me to|is there anything else|I hope this helps|happy to help)\b", "WARN", "en"),
    ("chatter", "letter opening", r"\bI hope this (?:message|email) finds you well\b|\bI am writing to\b", "WARN", "en"),
    ("chatter", "closing offer", r"\b(?:no dudes en|quedo a (?:tu|su) disposición|espero que (?:esto|esta información) (?:te|le|os) (?:ayude|sirva))\b", "WARN", "es"),
    ("chatter", "closing offer", "¿(?:quieres|te gustaría|desea[s]?) que\\b", "WARN", "es"),
    ("chatter", "agreement opener", r"\btienes toda la razón\b", "WARN", "es"),
    ("chatter", "letter opening", r"\bespero que (?:este mensaje|te encuentres)\b|\bme pongo en contacto contigo para\b", "WARN", "es"),
    ("hedge", "source-availability hedge", r"\b(?:while specific details are (?:limited|scarce)|not widely (?:available|documented|disclosed)|based on (?:the )?available information|in the (?:provided|available) sources)\b", "WARN", "en"),
    # Content.
    ("puffery", "avoided copula", r"\b(?:stands|serves|functions|operates) as\b", "WARN", "en"),
    ("puffery", "inflated significance", r"\bis an? (?:testament|reminder)\b|\bplay(?:s|ed|ing)? an? (?:crucial|pivotal|vital|key|significant) role\b|\b(?:underscore|highlight)s? (?:its|the|their) (?:importance|significance)\b|\breflects? broader\b|\bsetting the stage for\b|\bevolving landscape\b|\bfocal point\b|\bindelible mark\b|\bdeeply rooted\b|\bkey turning point\b|\bmarks? a (?:shift|turning point|milestone)\b", "WARN", "en"),
    ("puffery", "promotional wording", r"\b(?:nestled|in the heart of|groundbreaking|renowned|diverse array|commitment to|natural beauty|boasts an?)\b", "WARN", "en"),
    ("puffery", "avoided copula", r"\bse (?:erige|posiciona) como\b", "WARN", "es"),
    ("puffery", "inflated significance", r"\b(?:desempeña|juega)n? un papel (?:crucial|fundamental|clave|vital|esencial|decisivo)\b|\b(?:un|es un) (?:testimonio|reflejo) de\b|\bpone de (?:manifiesto|relieve)\b|\bmarca un antes y un después\b|\ben el panorama actual\b|\ben un mundo cada vez más\b|\bsubraya la importancia\b|\bsin precedentes\b", "WARN", "es"),
    ("weasel", "vague attribution", r"\bexperts (?:argue|say|believe|agree|note)\b|\bobservers have\b|\bsome critics\b|\bindustry reports\b|\bstudies (?:show|suggest)\b", "WARN", "en"),
    ("weasel", "vague attribution", r"\blos expertos (?:señalan|afirman|coinciden|consideran|apuntan)\b|\bdiversos estudios\b|\bsegún (?:varias|diversas) fuentes\b", "WARN", "es"),
    ("outline", "challenges-and-outlook closer", r"\bdespite these challenges\b|\bfuture outlook\b|\bfaces several challenges\b", "WARN", "en"),
    # Grammar.
    ("parallelism", "not X but Y", r"\bnot (?:just|only|merely|simply)\b[^.?!\n]{0,120}\bbut\b", "WARN", "en"),
    ("parallelism", "it's not X, it's Y", r"\b(?:it|this|that)" + APOS + r"?s not\b[^.?!\n,;]{1,60}[,;] (?:it|this|that)" + APOS + r"?s\b|\bisn" + APOS + r"t (?:just )?about\b[^.?!\n]{0,80}\bit" + APOS + r"s about\b", "WARN", "en"),
    ("parallelism", "no solo X sino Y", r"\bno (?:solo|sólo|solamente|únicamente)\b[^.?!\n]{0,120}\bsino\b|\bno se trata (?:solo |sólo )?de\b[^.?!\n]{0,120}\bsino\b", "WARN", "es"),
    ("participle", "participle tail", r",\s+(?:highlighting|underscoring|emphasizing|emphasising|ensuring|reflecting|symbolizing|contributing to|fostering|cultivating|showcasing|enhancing|reinforcing|solidifying|cementing)\b", "WARN", "en"),
    ("participle", "gerundio de cola", r",\s+(?:destacando|subrayando|resaltando|garantizando|asegurando|reflejando|fomentando|potenciando|consolidando|reforzando|impulsando|evidenciando)\b", "WARN", "es"),
    ("didactic", "didactic disclaimer", r"\bit(?:" + APOS + r"s| is) (?:important|crucial|essential|worth) (?:to note|noting|to remember|to consider|mentioning)\b|\bworth noting\b|\bmay vary\b", "WARN", "en"),
    ("didactic", "summary opener", SOS + r"(?:in summary|in conclusion|to sum up|overall|ultimately),", "WARN", "en"),
    ("didactic", "didactic disclaimer", r"\bes (?:importante|fundamental|crucial|esencial) (?:destacar|señalar|tener en cuenta|mencionar|recordar|subrayar)\b|\bcabe (?:destacar|señalar|mencionar|resaltar)\b|\bvale la pena (?:mencionar|destacar|señalar)\b", "WARN", "es"),
    ("didactic", "summary opener", SOS + r"(?:en resumen|en conclusión|en definitiva|en síntesis),", "WARN", "es"),
]

VOCAB = {
    "en": r"additionally|align(?:s|ed)? with|bolster(?:s|ed|ing)?|boast(?:s|ed|ing)?|crucial|deep dive|delv(?:e|es|ed|ing)|emphasiz(?:e|es|ed|ing)|enduring|enhanc(?:e|es|ed|ing|ement)|foster(?:s|ed|ing)?|garner(?:s|ed|ing)?|highlight(?:s|ed|ing)?|interplay|intricat(?:e|ely)|intricac(?:y|ies)|landscape|meticulous(?:ly)?|pivotal|robust|showcas(?:e|es|ed|ing)|tapestry|testament|underscor(?:e|es|ed|ing)|vibrant|leverag(?:e|es|ed|ing)|multifaceted|seamless(?:ly)?|holistic|realm|nuanced|empower(?:s|ed|ing)?|quietly|universally",
    "es": "crucial(?:es)?|fundamental(?:es)?|robust[oa]s?|potenci(?:ar|a|an|ando|ado)|foment(?:ar|a|an|ando)|profundiz(?:ar|a|an|ando)|sumerg(?:irse|irnos|imos)|adentr(?:arse|arnos)|testimonio|holístic[oa]s?|multifacétic[oa]s?|revolucionari[oa]s?|innovador(?:a|es|as)?|esencial(?:es)?|aborda(?:r|mos|ndo)?|primordial(?:es)?|panorama|ecosistema|sinergia(?:s)?",
}
VOCAB_WARN_HITS = 6
VOCAB_DENSITY_HITS = 3
VOCAB_DENSITY_PER_100 = 1.0

SMALL_WORDS = set(
    "a an and as at but by for from in into nor of on or per the to vs via with "
    "y e o u de del la las el los en con por para sin un una al".split()
)
EMOJI = "[\U0001F300-\U0001FAFF☀-➿⭐]"


def strip_for_prose(text):
    """Blank out frontmatter, fenced code, quoted lines and inline code, keeping line numbers."""
    lines = text.split("\n")
    out = []
    fence = None
    in_front = bool(lines) and lines[0].strip() == "---"
    for i, line in enumerate(lines):
        s = line.strip()
        if in_front:
            out.append("")
            if i > 0 and s == "---":
                in_front = False
            continue
        if fence:
            out.append("")
            if s.startswith(fence):
                fence = None
            continue
        m = re.match(r"(```+|~~~+)", s)
        if m:
            fence = m.group(1)
            out.append("")
            continue
        if s.startswith(">"):
            out.append("")
            continue
        out.append(re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)), line))
    return out


def find_lines(lines, regex, flags=I):
    pat = re.compile(regex, flags | re.MULTILINE)
    for n, line in enumerate(lines, 1):
        for m in pat.finditer(line):
            yield n, m.group(0)


def short(s, width=60):
    s = " ".join(s.split())
    return s if len(s) <= width else s[: width - 3] + "..."


def scan(text, langs):
    findings = []  # (level, line, category, detail)
    raw_lines = text.split("\n")
    lines = strip_for_prose(text)
    prose = "\n".join(lines)
    words = re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", prose)
    n_words = len(words)

    for label, regex in ARTIFACTS:
        for n, hit in find_lines(raw_lines, regex, 0):
            findings.append(("HARD", n, "artifact", "%s (%s)" % (label, short(hit, 30))))
    for label, regex, flags in PLACEHOLDERS:
        for n, hit in find_lines(lines, regex, flags):
            findings.append(("HARD", n, "placeholder", "%s: %s" % (label, short(hit))))
    for n, line in enumerate(lines, 1):
        if "\u2014" in line:
            findings.append(("HARD", n, "character", "em dash (U+2014): use a comma, colon, parentheses or '-'"))

    curly = [n for n, line in enumerate(lines, 1) if re.search("[“”‘’]", line)]
    if curly:
        findings.append(("WARN", curly[0], "character",
                         "curly quotes or apostrophes on %d line(s), first at line %d: use straight ' and \""
                         % (len(curly), curly[0])))

    for category, label, regex, level, lang in PHRASES:
        if lang not in langs:
            continue
        for n, hit in find_lines(lines, regex):
            findings.append((level, n, category, '%s: "%s"' % (label, short(hit.strip()))))

    counts = {}
    for lang in langs:
        for _, hit in find_lines(lines, r"\b(?:%s)\b" % VOCAB[lang]):
            key = hit.lower()
            counts[key] = counts.get(key, 0) + 1
    hits = sum(counts.values())
    if hits:
        per_100 = 100.0 * hits / max(n_words, 1)
        listed = ", ".join(k if v == 1 else "%s x%d" % (k, v) for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
        dense = hits >= VOCAB_WARN_HITS or (hits >= VOCAB_DENSITY_HITS and per_100 >= VOCAB_DENSITY_PER_100)
        findings.append(("WARN" if dense else "NOTE", 0, "vocabulary",
                         "%d AI-vocabulary hit(s) in %d words (%.1f per 100): %s" % (hits, n_words, per_100, listed)))

    findings.extend(format_checks(lines, n_words))
    findings.extend(rhythm_check(lines))
    return findings, n_words


def format_checks(lines, n_words):
    out = []
    for n, line in enumerate(lines, 1):
        m = re.match(r"\s*#{1,6}\s+(.+)", line)
        if not m:
            continue
        heading = re.sub(EMOJI, "", m.group(1)).strip()
        tokens = re.findall(r"[^\W\d_][\w'’-]*", heading)
        rest = [w for w in tokens[1:] if w.lower() not in SMALL_WORDS and len(w) > 3]
        if len(rest) >= 2 and all(w[0].isupper() for w in rest) and not heading.isupper():
            out.append(("WARN", n, "format", 'Title Case heading: "%s" (use sentence case)' % short(heading)))

    def aggregate(regex, minimum, label):
        hit = [n for n, line in enumerate(lines, 1) if re.search(regex, line)]
        if len(hit) >= minimum:
            out.append(("WARN", hit[0], "format", "%s on %d line(s), first at line %d" % (label, len(hit), hit[0])))

    aggregate(r"^\s*(?:[-*+]|\d+[.)])\s+\*\*[^*\n]+?(?::\*\*|\*\*\s*:)", 3,
              "inline-header list items (- **Label:** text): prefer prose or a table")
    aggregate("^\\s*[•–]\\s", 1, "pasted bullet characters (• or –): use - for lists")
    aggregate(r"^\s*(?:#{1,6}|[-*+]|\d+[.)])\s*" + EMOJI, 2, "emoji at the start of headings or bullets")
    aggregate(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", 2, "thematic breaks between sections")

    bold = sum(len(re.findall(r"\*\*[^*\n]+\*\*", line)) for line in lines)
    if bold >= 5 and bold * 40 > n_words:
        out.append(("WARN", 0, "format", "%d bold spans in %d words: keep bold for the one thing that must not be missed" % (bold, n_words)))
    return out


def rhythm_check(lines):
    paras = [l for l in lines if l.strip() and not re.match(r"\s*(?:#|\||[-*+]\s|\d+[.)]\s)", l)]
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(paras))
    lengths = [len(s.split()) for s in sentences if len(s.split()) >= 3]
    if len(lengths) < 8:
        return []
    mean = statistics.mean(lengths)
    cv = statistics.pstdev(lengths) / mean if mean else 0
    if cv < 0.3:
        return [("WARN", 0, "rhythm",
                 "%d sentences of near-identical length (mean %.0f words, variation %.2f): mix short and long ones"
                 % (len(lengths), mean, cv))]
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description="Flag AI-writing tells in a draft.")
    ap.add_argument("file", nargs="?", help="draft to check (default: stdin)")
    ap.add_argument("--lang", choices=("en", "es", "all"), default="all")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 64

    if args.file:
        try:
            with open(args.file, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            print("ai-tells: cannot read %s: %s" % (args.file, exc.strerror), file=sys.stderr)
            return 64
        name = args.file
    else:
        text = sys.stdin.read()
        name = "stdin"

    langs = ("en", "es") if args.lang == "all" else (args.lang,)
    findings, n_words = scan(text, langs)
    order = {"HARD": 0, "WARN": 1, "NOTE": 2}
    findings.sort(key=lambda f: (order[f[0]], f[1], f[2]))

    hard = sum(1 for f in findings if f[0] == "HARD")
    warn = sum(1 for f in findings if f[0] == "WARN")
    if not findings:
        print("ai-tells: %s clean (%d words)" % (name, n_words))
        return 0
    print("ai-tells: %s, %d words" % (name, n_words))
    for level, line, category, detail in findings:
        print("  %-4s  %-5s %-11s %s" % (level, "L%d" % line if line else "-", category, detail))
    if hard or warn:
        print("%d hard, %d warning(s). Rewrite them (skill human-writing); hard ones must go." % (hard, warn))
    return 2 if hard else 1 if warn else 0


if __name__ == "__main__":
    sys.exit(main())
