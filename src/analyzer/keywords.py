"""Keyword extraction from text using basic NLP techniques.

This module provides keyword extraction without requiring spaCy models to be
downloaded. It uses regex-based noun phrase extraction and frequency analysis.
When spaCy is available, it will use it for better quality extraction.
"""

import re
from collections import Counter
from dataclasses import dataclass, field


# ── Common stop words to filter out ──────────────────────────

STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "must",
    "it", "its", "this", "that", "these", "those", "i", "you", "he",
    "she", "we", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "our", "their", "what", "which", "who", "whom", "where",
    "when", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "about", "above", "after",
    "again", "also", "any", "because", "before", "between", "during",
    "into", "through", "under", "until", "up", "out", "over",
    "including", "using", "working", "work", "experience", "role",
    "team", "company", "position", "looking", "strong", "ability",
    "etc", "e.g", "i.e", "well", "new", "required", "preferred",
    "plus", "bonus", "ideal", "minimum", "least", "years", "year",
})

# ── Known technical skill aliases ────────────────────────────

SKILL_ALIASES: dict[str, str] = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "py": "Python",
    "python": "Python",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "angular": "Angular",
    "angularjs": "Angular",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "spring": "Spring",
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google cloud": "GCP",
    "azure": "Azure",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "graphql": "GraphQL",
    "rest": "REST",
    "restful": "REST",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "linux": "Linux",
    "sql": "SQL",
    "nosql": "NoSQL",
    "html": "HTML",
    "css": "CSS",
    "sass": "SASS",
    "scss": "SASS",
    "webpack": "Webpack",
    "nginx": "Nginx",
    "apache": "Apache",
    "elasticsearch": "Elasticsearch",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "nlp": "NLP",
    "natural language processing": "NLP",
    "ai": "AI",
    "artificial intelligence": "AI",
    "agile": "Agile",
    "scrum": "Scrum",
    "jira": "Jira",
    "jenkins": "Jenkins",
}


@dataclass
class Keyword:
    """A single extracted keyword."""
    text: str
    canonical: str  # Normalized/canonical form
    frequency: int = 1
    category: str = "general"  # skill | tool | soft_skill | general


@dataclass
class KeywordExtractionResult:
    """Result of keyword extraction from text."""
    keywords: list[Keyword] = field(default_factory=list)
    raw_text: str = ""

    @property
    def keyword_names(self) -> list[str]:
        return [k.canonical for k in self.keywords]

    def get_by_category(self, category: str) -> list[Keyword]:
        return [k for k in self.keywords if k.category == category]


def normalize_keyword(text: str) -> str:
    """Normalize a keyword to its canonical form."""
    lower = text.strip().lower()
    return SKILL_ALIASES.get(lower, text.strip())


def _extract_technical_terms(text: str) -> list[str]:
    """Extract technical terms using pattern matching."""
    # Match known technology patterns (case-insensitive)
    patterns = [
        r'\b(?:' + '|'.join(re.escape(k) for k in SKILL_ALIASES.keys()) + r')\b',
        # Match capitalized tech terms like "React", "Docker", "PostgreSQL"
        r'\b[A-Z][a-z]+(?:\.[a-z]+)?\b',
        # Match ALL-CAPS acronyms (AWS, GCP, SQL, REST, etc.)
        r'\b[A-Z]{2,6}\b',
        # Match terms with dots like "Node.js", "Vue.js"
        r'\b\w+\.\w+\b',
    ]

    terms = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        terms.extend(matches)
    return terms


def _extract_ngrams(text: str, n: int = 2) -> list[str]:
    """Extract meaningful n-grams (bigrams by default)."""
    words = re.findall(r'\b[a-z]+\b', text.lower())
    words = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    ngrams = []
    for i in range(len(words) - n + 1):
        ngram = " ".join(words[i:i + n])
        ngrams.append(ngram)
    return ngrams


def extract_keywords(text: str, max_keywords: int = 30) -> KeywordExtractionResult:
    """Extract keywords from text using frequency analysis and pattern matching.

    Args:
        text: Input text (resume or job description).
        max_keywords: Maximum number of keywords to return.

    Returns:
        KeywordExtractionResult with ranked keywords.
    """
    if not text or not text.strip():
        return KeywordExtractionResult(raw_text=text)

    # 1. Extract technical terms via pattern matching
    tech_terms = _extract_technical_terms(text)

    # 2. Extract single meaningful words
    words = re.findall(r'\b[a-z][a-z-]+\b', text.lower())
    words = [w for w in words if w not in STOP_WORDS and len(w) > 2]

    # 3. Extract bigrams
    bigrams = _extract_ngrams(text, n=2)

    # 4. Count frequencies
    all_terms = tech_terms + words
    freq = Counter()
    for term in all_terms:
        canonical = normalize_keyword(term)
        if canonical.lower() not in STOP_WORDS and len(canonical) > 1:
            freq[canonical] += 1

    # 5. Also count bigrams (lower weight)
    bigram_freq = Counter(bigrams)

    # 6. Build keyword list
    keywords: dict[str, Keyword] = {}

    for term, count in freq.most_common(max_keywords * 2):
        canonical = normalize_keyword(term)
        if canonical not in keywords:
            # Determine category
            if canonical.lower() in SKILL_ALIASES or canonical in SKILL_ALIASES.values():
                category = "skill"
            elif any(c.isupper() for c in canonical) and len(canonical) <= 15:
                category = "tool"
            else:
                category = "general"

            keywords[canonical] = Keyword(
                text=term,
                canonical=canonical,
                frequency=count,
                category=category,
            )

    # 7. Sort by frequency descending
    sorted_keywords = sorted(keywords.values(), key=lambda k: k.frequency, reverse=True)

    return KeywordExtractionResult(
        keywords=sorted_keywords[:max_keywords],
        raw_text=text,
    )


def extract_keywords_with_importance(
    jd_text: str,
    max_keywords: int = 30,
) -> list[dict]:
    """Extract keywords with importance weighting based on position and frequency.

    Keywords appearing in the first half of the JD (usually requirements)
    get a higher importance weight than those in the second half.

    Returns:
        List of dicts with keys: keyword, category, importance, frequency.
    """
    result = extract_keywords(jd_text, max_keywords=max_keywords)
    midpoint = len(jd_text) // 2

    weighted = []
    for kw in result.keywords:
        # Check if keyword appears in the first half (requirements section)
        first_pos = jd_text.lower().find(kw.canonical.lower())
        if first_pos == -1:
            first_pos = jd_text.lower().find(kw.text.lower())

        if first_pos < midpoint:
            importance = "high"
        elif kw.frequency >= 3:
            importance = "high"
        elif kw.frequency >= 2:
            importance = "medium"
        else:
            importance = "low"

        weighted.append({
            "keyword": kw.canonical,
            "category": kw.category,
            "importance": importance,
            "frequency": kw.frequency,
        })

    return weighted
