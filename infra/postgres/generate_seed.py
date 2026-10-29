"""Generate 03_seed.sql: demo data for both data-owning systems.

    uv run python infra/postgres/generate_seed.py

Names are real people and organisations; dates and descriptions are simplified demo data,
not a reference source. The Hall of Fame part (collections, notes) is entirely fake and is
generated from templates with a fixed random seed, so the output is reproducible.
"""

from __future__ import annotations

import random
from pathlib import Path

OUT = Path(__file__).with_name("03_seed.sql")
RNG = random.Random(42)

# slug, name, born, died, country, known_for, bio
FIGURES = [
    (
        "steve-jobs",
        "Steve Jobs",
        1955,
        2011,
        "United States",
        "Apple, Macintosh, iPhone",
        "Co-founded Apple, founded NeXT, led Pixar, returned to Apple and launched the iPod and iPhone.",
    ),
    (
        "steve-wozniak",
        "Steve Wozniak",
        1950,
        None,
        "United States",
        "Apple I and Apple II",
        "Engineer who designed the Apple I and Apple II personal computers.",
    ),
    (
        "bill-gates",
        "Bill Gates",
        1955,
        None,
        "United States",
        "Microsoft, MS-DOS, Windows",
        "Co-founded Microsoft and led it through MS-DOS and Windows.",
    ),
    (
        "ada-lovelace",
        "Ada Lovelace",
        1815,
        1852,
        "United Kingdom",
        "First published algorithm",
        "Wrote notes on Babbage's Analytical Engine that include an algorithm for a machine.",
    ),
    (
        "alan-turing",
        "Alan Turing",
        1912,
        1954,
        "United Kingdom",
        "Turing machine, codebreaking",
        "Formalised computation with the Turing machine and worked on wartime codebreaking.",
    ),
    (
        "grace-hopper",
        "Grace Hopper",
        1906,
        1992,
        "United States",
        "Compilers, COBOL",
        "Built one of the first compilers and pushed for English-like programming languages.",
    ),
    (
        "linus-torvalds",
        "Linus Torvalds",
        1969,
        None,
        "Finland",
        "Linux, Git",
        "Started the Linux kernel as a student and later wrote Git.",
    ),
    (
        "tim-berners-lee",
        "Tim Berners-Lee",
        1955,
        None,
        "United Kingdom",
        "World Wide Web",
        "Invented the World Wide Web at CERN and founded the W3C.",
    ),
    (
        "margaret-hamilton",
        "Margaret Hamilton",
        1936,
        None,
        "United States",
        "Apollo flight software",
        "Led the team that wrote the on-board flight software for the Apollo missions.",
    ),
    (
        "dennis-ritchie",
        "Dennis Ritchie",
        1941,
        2011,
        "United States",
        "C language, Unix",
        "Created the C programming language and co-created Unix at Bell Labs.",
    ),
    (
        "jensen-huang",
        "Jensen Huang",
        1963,
        None,
        "United States",
        "NVIDIA, GPUs, CUDA",
        "Co-founded NVIDIA and led it from graphics chips to GPU computing.",
    ),
    (
        "fei-fei-li",
        "Fei-Fei Li",
        1976,
        None,
        "United States",
        "ImageNet, computer vision",
        "Created the ImageNet dataset that helped start the deep learning era in vision.",
    ),
]

# slug, name, kind, founded, location
ORGANIZATIONS = [
    ("apple", "Apple", "company", 1976, "Cupertino, California"),
    ("next", "NeXT", "company", 1985, "Redwood City, California"),
    ("pixar", "Pixar", "company", 1986, "Emeryville, California"),
    ("microsoft", "Microsoft", "company", 1975, "Redmond, Washington"),
    ("nvidia", "NVIDIA", "company", 1993, "Santa Clara, California"),
    ("bell-labs", "Bell Labs", "lab", 1925, "Murray Hill, New Jersey"),
    ("cern", "CERN", "lab", 1954, "Geneva, Switzerland"),
    ("w3c", "World Wide Web Consortium", "nonprofit", 1994, "Cambridge, Massachusetts"),
    ("mit-instrumentation-lab", "MIT Instrumentation Laboratory", "lab", 1932, "Cambridge, Massachusetts"),
    ("bletchley-park", "Bletchley Park", "lab", 1938, "Milton Keynes, England"),
    ("remington-rand", "Remington Rand", "company", 1927, "New York, New York"),
    ("stanford", "Stanford University", "university", 1885, "Stanford, California"),
    ("linux-foundation", "Linux Foundation", "nonprofit", 2007, "San Francisco, California"),
]

# figure, organization, role, from_year
AFFILIATIONS = [
    ("steve-jobs", "apple", "co-founder", 1976),
    ("steve-jobs", "next", "founder", 1985),
    ("steve-jobs", "pixar", "CEO", 1986),
    ("steve-wozniak", "apple", "co-founder", 1976),
    ("bill-gates", "microsoft", "co-founder", 1975),
    ("alan-turing", "bletchley-park", "codebreaker", 1939),
    ("grace-hopper", "remington-rand", "programmer", 1950),
    ("linus-torvalds", "linux-foundation", "fellow", 2007),
    ("tim-berners-lee", "cern", "researcher", 1984),
    ("tim-berners-lee", "w3c", "founder", 1994),
    ("margaret-hamilton", "mit-instrumentation-lab", "software lead", 1961),
    ("dennis-ritchie", "bell-labs", "researcher", 1967),
    ("jensen-huang", "nvidia", "co-founder", 1993),
    ("fei-fei-li", "stanford", "professor", 2009),
]

# slug, name, year, category, organization, lead figure, description
PRODUCTS = [
    (
        "apple-i",
        "Apple I",
        1976,
        "computer",
        "apple",
        "steve-wozniak",
        "Single-board computer sold as a kit.",
    ),
    (
        "apple-ii",
        "Apple II",
        1977,
        "computer",
        "apple",
        "steve-wozniak",
        "Early mass-market personal computer.",
    ),
    (
        "macintosh",
        "Macintosh",
        1984,
        "computer",
        "apple",
        "steve-jobs",
        "Personal computer with a graphical UI.",
    ),
    (
        "next-computer",
        "NeXT Computer",
        1988,
        "computer",
        "next",
        "steve-jobs",
        "Workstation for higher education.",
    ),
    ("ipod", "iPod", 2001, "device", "apple", "steve-jobs", "Portable music player."),
    ("iphone", "iPhone", 2007, "device", "apple", "steve-jobs", "Touchscreen smartphone."),
    ("toy-story", "Toy Story", 1995, "film", "pixar", None, "First fully computer-animated feature film."),
    (
        "altair-basic",
        "Altair BASIC",
        1975,
        "software",
        "microsoft",
        "bill-gates",
        "BASIC interpreter for the Altair.",
    ),
    (
        "ms-dos",
        "MS-DOS",
        1981,
        "software",
        "microsoft",
        "bill-gates",
        "Operating system for IBM PC compatibles.",
    ),
    ("windows-1", "Windows 1.0", 1985, "software", "microsoft", "bill-gates", "First version of Windows."),
    ("note-g", "Note G", 1843, "algorithm", None, "ada-lovelace", "Algorithm for Bernoulli numbers."),
    (
        "turing-machine",
        "On Computable Numbers",
        1936,
        "paper",
        None,
        "alan-turing",
        "Introduced the Turing machine.",
    ),
    (
        "bombe",
        "Bombe",
        1940,
        "machine",
        "bletchley-park",
        "alan-turing",
        "Electromechanical codebreaking machine.",
    ),
    ("a-0", "A-0 System", 1952, "software", "remington-rand", "grace-hopper", "Early compiler."),
    ("cobol", "COBOL", 1959, "language", None, "grace-hopper", "Business programming language."),
    (
        "linux",
        "Linux kernel",
        1991,
        "software",
        None,
        "linus-torvalds",
        "Open-source operating system kernel.",
    ),
    ("git", "Git", 2005, "software", None, "linus-torvalds", "Distributed version control system."),
    ("www", "WorldWideWeb", 1990, "software", "cern", "tim-berners-lee", "First web browser and editor."),
    (
        "agc-software",
        "Apollo flight software",
        1969,
        "software",
        "mit-instrumentation-lab",
        "margaret-hamilton",
        "On-board guidance software for Apollo.",
    ),
    ("unix", "Unix", 1971, "software", "bell-labs", "dennis-ritchie", "Multi-user operating system."),
    ("c-language", "C", 1972, "language", "bell-labs", "dennis-ritchie", "Systems programming language."),
    (
        "geforce-256",
        "GeForce 256",
        1999,
        "chip",
        "nvidia",
        "jensen-huang",
        "Graphics chip marketed as the first GPU.",
    ),
    (
        "cuda",
        "CUDA",
        2007,
        "platform",
        "nvidia",
        "jensen-huang",
        "Platform for general-purpose GPU computing.",
    ),
    ("imagenet", "ImageNet", 2009, "dataset", "stanford", "fei-fei-li", "Large labelled image dataset."),
]

NOTE_TEMPLATES = [
    "Read about {name} today: {known_for}. Worth a second look.",
    "{name} is a good example of turning an idea into a product.",
    "Compare {name} with someone from a different decade.",
    "Question for later: what did {name} build before becoming famous?",
]


def sql(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def row(*values: object) -> str:
    return "(" + ", ".join(sql(v) for v in values) + ")"


def ref(table: str, slug: str | None) -> str:
    return "NULL" if slug is None else f"(SELECT id FROM legends.{table} WHERE slug = {sql(slug)})"


def legends_sql() -> list[str]:
    out = ["INSERT INTO legends.figures (slug, name, born, died, country, known_for, bio) VALUES"]
    out.append(",\n".join(row(*f) for f in FIGURES) + ";")
    out.append("INSERT INTO legends.organizations (slug, name, kind, founded, location) VALUES")
    out.append(",\n".join(row(*o) for o in ORGANIZATIONS) + ";")
    for figure, org, role, year in AFFILIATIONS:
        out.append(
            "INSERT INTO legends.affiliations (figure_id, organization_id, role, from_year) VALUES "
            f"({ref('figures', figure)}, {ref('organizations', org)}, {sql(role)}, {year});"
        )
    for slug, name, year, category, org_slug, lead_slug, desc in PRODUCTS:
        out.append(
            "INSERT INTO legends.products (slug, name, year, category, organization_id, lead_figure_id, "
            f"description) VALUES ({sql(slug)}, {sql(name)}, {year}, {sql(category)}, "
            f"{ref('organizations', org_slug)}, {ref('figures', lead_slug)}, {sql(desc)});"
        )
    return out + milestones_sql()


def milestones_sql() -> list[str]:
    """Generated timeline: birth, each product launch, each affiliation start."""
    events: list[tuple[str, int, str]] = [(f[0], f[2], f"Born in {f[4]}") for f in FIGURES]
    events += [(p[5], p[2], f"Released {p[1]}") for p in PRODUCTS if p[5]]
    names = {o[0]: o[1] for o in ORGANIZATIONS}
    events += [(a[0], a[3], f"Joined {names[a[1]]} as {a[2]}") for a in AFFILIATIONS]
    return [
        "INSERT INTO legends.milestones (figure_id, year, title) "
        f"VALUES ({ref('figures', s)}, {y}, {sql(t)});"
        for s, y, t in sorted(events, key=lambda e: (e[0], e[1]))
    ]


def halloffame_sql() -> list[str]:
    out = [
        "INSERT INTO halloffame.collections (owner, name, description) VALUES",
        ",\n".join(
            [
                row("ada", "Founders", "People who started companies"),
                row("ada", "Language makers", "Creators of programming languages"),
                row("linus", "Open source", "People behind open-source software"),
            ]
        )
        + ";",
    ]
    picks = {
        1: ["steve-jobs", "bill-gates", "jensen-huang"],
        2: ["dennis-ritchie", "grace-hopper"],
        3: ["linus-torvalds", "tim-berners-lee"],
    }
    for collection_id, slugs in picks.items():
        out += [f"INSERT INTO halloffame.collection_items VALUES ({collection_id}, {sql(s)});" for s in slugs]
    for _ in range(10):
        owner = RNG.choice(["ada", "linus"])
        figure = RNG.choice(FIGURES)
        slug, name, known_for = str(figure[0]), str(figure[1]), str(figure[5])
        body = RNG.choice(NOTE_TEMPLATES).format(name=name, known_for=known_for)
        out.append(
            f"INSERT INTO halloffame.notes (owner, figure_slug, body) VALUES {row(owner, slug, body)};"
        )
    return out


def main() -> None:
    header = ["-- GENERATED by generate_seed.py. Demo data, not a reference source. Do not edit by hand.", ""]
    OUT.write_text("\n".join(header + legends_sql() + [""] + halloffame_sql()) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
