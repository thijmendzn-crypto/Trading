"""
Knowledge engine: loads, chunks and retrieves content from the /knowledge directory.
Provides relevant context to the AI evaluator before every signal assessment.
"""
from pathlib import Path
from loguru import logger


class KnowledgeChunk:
    def __init__(self, source: str, heading: str, content: str):
        self.source = source
        self.heading = heading
        self.content = content

    def __repr__(self):
        return f"KnowledgeChunk({self.source} / {self.heading})"


class KnowledgeEngine:

    def __init__(self, knowledge_dir: str = "./knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self.chunks: list[KnowledgeChunk] = []
        self._load()

    def _load(self):
        """Load and chunk all markdown files in the knowledge directory."""
        if not self.knowledge_dir.exists():
            logger.warning(f"Knowledge directory not found: {self.knowledge_dir}")
            return

        for md_file in sorted(self.knowledge_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
                chunks = self._chunk_file(content, md_file.name)
                self.chunks.extend(chunks)
                logger.debug(f"Loaded {len(chunks)} chunks from {md_file.name}")
            except Exception as e:
                logger.error(f"Failed to load {md_file.name}: {e}")

        logger.info(f"Knowledge base loaded: {len(self.chunks)} total chunks")

    def _chunk_file(self, content: str, filename: str) -> list[KnowledgeChunk]:
        """Split a markdown file into sections by ## headings."""
        chunks = []
        current_heading = filename.replace(".md", "").replace("-", " ").title()
        current_content = ""

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_content.strip():
                    chunks.append(KnowledgeChunk(filename, current_heading, current_content.strip()))
                current_heading = line.lstrip("# ").strip()
                current_content = ""
            elif line.startswith("# "):
                # Top-level heading — treat as intro chunk
                if current_content.strip():
                    chunks.append(KnowledgeChunk(filename, current_heading, current_content.strip()))
                current_heading = line.lstrip("# ").strip()
                current_content = ""
            else:
                current_content += line + "\n"

        if current_content.strip():
            chunks.append(KnowledgeChunk(filename, current_heading, current_content.strip()))

        return chunks

    def get_relevant_context(self, query: str, max_chunks: int = 10) -> str:
        """
        Retrieve the most relevant knowledge chunks for a given query.
        Uses keyword scoring — production upgrade: pgvector semantic search.
        """
        query_terms = set(query.lower().split())

        # Score each chunk by keyword overlap
        scored = []
        for chunk in self.chunks:
            text = (chunk.heading + " " + chunk.content).lower()
            score = sum(text.count(term) for term in query_terms)

            # Boost certain always-relevant files
            if chunk.source in ("strategy-framework.md", "risk-management.md"):
                score += 3

            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [chunk for _, chunk in scored[:max_chunks] if _ > 0]

        if not top:
            # Fallback: return first chunks from core files
            top = [c for c in self.chunks if c.source in (
                "strategy-framework.md", "risk-management.md", "market-regimes.md"
            )][:6]

        sections = []
        for chunk in top:
            sections.append(f"### [{chunk.source}] {chunk.heading}\n{chunk.content}")

        return "\n\n---\n\n".join(sections)

    def get_full_context(self) -> str:
        """Return the entire knowledge base as a single string (for system prompt)."""
        sections = []
        for chunk in self.chunks:
            sections.append(f"### [{chunk.source}] {chunk.heading}\n{chunk.content}")
        return "\n\n---\n\n".join(sections)

    def reload(self):
        """Reload the knowledge base (hot-reload support)."""
        self.chunks = []
        self._load()
        logger.info("Knowledge base reloaded")
