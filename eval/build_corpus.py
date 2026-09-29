"""Generate a fictional corpus (so answers can't come from model memory) and a golden Q&A set.

Each golden item has `evidence`: verbatim quote(s) from the corpus that answer it. Scoring checks whether
retrieved chunks contain those quotes, so it is independent of chunk ids / re-chunking.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core import config, llm

ROOT = config.ROOT
TOPICS = [
    "Meridian Robotics, a warehouse automation company: history, founders, products, revenue, offices, incidents",
    "The Halvorsen Basin Water Authority: dams, treatment plants, tariffs, drought policy, key officials",
    "Kestrel Airlines: fleet, routes, safety record, loyalty program, labor disputes, hubs",
    "Orsino Pharmaceuticals: drug pipeline, clinical trials, patents, manufacturing sites, leadership",
    "The Tessaly Municipal Transit System: lines, ridership numbers, fares, construction projects, governance",
    "Brightwater University: colleges, tuition, research centers, endowment, notable alumni, campus policies",
    "Lumen Grid Energy: power plants, capacity in MW, outages, regulation, renewable targets, pricing",
    "The Varga Archipelago Tourism Board: islands, visitor stats, ferry schedules, conservation rules, festivals",
    "Corvane Airways: fleet, routes, safety record, loyalty program, labor disputes, hubs",
    "Northgate Robotics, a surgical robotics company: history, founders, products, revenue, offices, incidents",
    "The Ostrava Coast Water Board: reservoirs, treatment plants, tariffs, drought policy, key officials",
    "Valdris Therapeutics: drug pipeline, clinical trials, patents, manufacturing sites, leadership",
    "The Pellham Regional Rail Authority: lines, ridership numbers, fares, construction projects, governance",
    "Ashcombe Institute of Technology: colleges, tuition, research centers, endowment, notable alumni, campus policies",
    "Solmere Power Cooperative: power plants, capacity in MW, outages, regulation, renewable targets, pricing",
    "The Ionic Isles Visitor Bureau: islands, visitor stats, ferry schedules, conservation rules, festivals",
    "Quillon Logistics, a freight and warehousing company: history, founders, depots, revenue, incidents",
    "The Marrow Valley Public Health Agency: hospitals, vaccination programs, budgets, outbreaks, officials",
    "Tarn Aerospace: satellites, launch vehicles, contracts, facilities, leadership, accidents",
    "The Eldergrove Metropolitan Library System: branches, collections, budgets, programs, policies",
]


def gen_doc(topic: str) -> str:
    return llm.chat([{"role": "user", "content":
        f"Write a detailed, dense, factual-sounding reference document (about 900 words, several sections with "
        f"markdown headings) about this entirely FICTIONAL subject: {topic}. Include many specific invented names, "
        f"dates, numbers, and policies. No disclaimers about fiction."}], temperature=0.9, max_tokens=2000)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_#>`]", "", s)).strip().lower()


def gen_single(title: str, text: str) -> list[dict]:
    r = llm.chat_json([{"role": "user", "content":
        f"Document:\n{text}\n\nWrite 4 diverse question/answer pairs answerable from ONE specific passage. "
        f"Mix paraphrased questions (little word overlap with the text) and exact-term questions (names, numbers). "
        f"For each give `evidence`: an EXACT verbatim sentence copied from the document containing the answer. "
        f"JSON: {{\"items\":[{{\"question\":..,\"answer\":..,\"evidence\":..}}]}}"}], temperature=0.5, max_tokens=1500)
    out = []
    for it in r.get("items", []):
        if norm(it.get("evidence", "")) and norm(it["evidence"]) in norm(text):
            out.append({"question": it["question"], "answer": it["answer"], "type": "single",
                        "evidence": [{"doc": title, "quote": it["evidence"]}]})
    return out


def gen_multi(a: tuple, b: tuple) -> list[dict]:
    r = llm.chat_json([{"role": "user", "content":
        f"Document A ({a[0]}):\n{a[1][:3500]}\n\nDocument B ({b[0]}):\n{b[1][:3500]}\n\n"
        f"Write 2 questions that REQUIRE facts from both documents (comparison or combined). For each give the "
        f"answer and `evidence_a`, `evidence_b`: EXACT verbatim sentences copied from each document. "
        f"JSON: {{\"items\":[{{\"question\":..,\"answer\":..,\"evidence_a\":..,\"evidence_b\":..}}]}}"}],
        temperature=0.5, max_tokens=1200)
    out = []
    for it in r.get("items", []):
        ea, eb = it.get("evidence_a", ""), it.get("evidence_b", "")
        if norm(ea) and norm(ea) in norm(a[1]) and norm(eb) and norm(eb) in norm(b[1]):
            out.append({"question": it["question"], "answer": it["answer"], "type": "multi",
                        "evidence": [{"doc": a[0], "quote": ea}, {"doc": b[0], "quote": eb}]})
    return out


def main():
    corpus = ROOT / "data" / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(8) as ex:
        texts = list(ex.map(gen_doc, TOPICS))
    docs = []
    for topic, text in zip(TOPICS, texts):
        title = topic.split(",")[0].split(":")[0].strip()
        (corpus / (title.replace(" ", "_") + ".md")).write_text(f"# {title}\n\n{text}", encoding="utf-8")
        docs.append((title, text))
    golden = []
    with ThreadPoolExecutor(8) as ex:
        for res in ex.map(lambda d: gen_single(*d), docs):
            golden += res
        pairs = [(docs[i], docs[(i + 1) % len(docs)]) for i in range(len(docs))] * 1
        for res in ex.map(lambda p: gen_multi(*p), pairs):
            golden += res
    for i, g in enumerate(golden):
        g["id"] = i + 1
    (ROOT / "eval" / "golden_set.json").write_text(json.dumps(golden, indent=2), encoding="utf-8")
    print(len(docs), "docs;", len(golden), "golden items;",
          sum(g["type"] == "multi" for g in golden), "multi-hop")


if __name__ == "__main__":
    main()
