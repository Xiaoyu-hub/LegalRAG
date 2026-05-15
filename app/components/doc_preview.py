def render_article_tree(chunks: list[dict]) -> dict:
    tree = {}
    for chunk in chunks:
        article = chunk.get("article", "General")
        section = chunk.get("section", "")
        subsection = chunk.get("subsection", "")

        if article not in tree:
            tree[article] = {"sections": {}}

        if section:
            if section not in tree[article]["sections"]:
                tree[article]["sections"][section] = {"chunks": []}
            tree[article]["sections"][section]["chunks"].append(chunk)
        else:
            tree[article].setdefault("chunks", []).append(chunk)

    return tree
