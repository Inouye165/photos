"""
Natural Language Query Parser & Intent Decomposer for LuminaPhoto.
Extracts clean visual concepts for CLIP, resolves entities/folders, parses temporal date bounds,
and detects classification filters from conversational queries.
"""

import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
from dateutil.relativedelta import relativedelta

# Conversational filler prefixes and phrases
CONVERSATIONAL_PREFIXES = [
    r"^show\s+me\s+(?:all\s+)?(?:photos?|pictures?|images?|pics?|screenshots?|files)?\s*(?:of|from|with|about)?\s*",
    r"^find\s+(?:me\s+)?(?:all\s+)?(?:photos?|pictures?|images?|pics?|screenshots?|files)?\s*(?:of|from|with|about)?\s*",
    r"^(?:where\s+are|look\s+for|search\s+for|display|bring\s+up)\s+(?:all\s+)?(?:photos?|pictures?|images?|pics?|screenshots?|files)?\s*(?:of|from|with|about)?\s*",
    r"^i\s+(?:want|would\s+like)\s+to\s+see\s+(?:all\s+)?(?:photos?|pictures?|images?|pics?|screenshots?|files)?\s*(?:of|from|with|about)?\s*",
    r"^can\s+you\s+(?:show|find)\s+(?:me\s+)?(?:all\s+)?(?:photos?|pictures?|images?|pics?|screenshots?|files)?\s*(?:of|from|with|about)?\s*",
    r"^(?:photos?|pictures?|pics?|images?|screenshots?)\s+(?:of|from|with|about)\s+"
]

MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12
}

SEASON_MONTHS = {
    "spring": (3, 5),
    "summer": (6, 8),
    "fall": (9, 11),
    "autumn": (9, 11),
    "winter": (12, 2)
}


class ParsedQuery:
    def __init__(
        self,
        raw_query: str,
        visual_prompt: str,
        entities: List[Dict[str, Any]],
        folder_keywords: List[str],
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        date_label: Optional[str] = None,
        classification: Optional[str] = "REAL_PHOTOS",
        temporal_phrase: Optional[str] = None,
        entity_ids: Optional[List[int]] = None,
        has_visual_scene: bool = True
    ):
        self.raw_query = raw_query
        self.visual_prompt = visual_prompt
        self.entities = entities  # list of {"id": 7, "name": "Ron", "type": "person"}
        self.folder_keywords = folder_keywords
        self.date_from = date_from
        self.date_to = date_to
        self.date_label = date_label
        self.classification = classification
        self.temporal_phrase = temporal_phrase
        self.entity_ids = entity_ids or []
        self.has_visual_scene = has_visual_scene

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "visual_prompt": self.visual_prompt,
            "entities": self.entities,
            "entity_ids": self.entity_ids,
            "has_visual_scene": self.has_visual_scene,
            "folder_keywords": self.folder_keywords,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "date_label": self.date_label,
            "classification": self.classification,
            "temporal_phrase": self.temporal_phrase
        }


class QueryParser:
    """Intelligent natural language query parser for photo collections."""

    DEFAULT_ALIASES = {
        "dobby": "dog",
        "puppy": "dog",
        "kitten": "cat"
    }

    def __init__(
        self,
        known_folders: Optional[List[str]] = None,
        reference_date: Optional[datetime] = None,
        entity_aliases: Optional[Dict[str, str]] = None,
        known_entities: Optional[List[Dict[str, Any]]] = None
    ):
        self.known_folders = [f.lower() for f in (known_folders or [])]
        self.reference_date = reference_date or datetime.now()
        self.entity_aliases = {**self.DEFAULT_ALIASES, **(entity_aliases or {})}
        # Sort known DB entities so active entities (with photos) and longer names match first
        raw_entities = [
            e for e in (known_entities or [])
            if isinstance(e, dict) and str(e.get("name", "")).strip()
        ]
        self.known_entities = sorted(
            raw_entities,
            key=lambda e: (1 if (e.get("total_photos") or 0) > 0 else 0, len(str(e["name"]).strip())),
            reverse=True
        )

    def parse(self, raw_query: str) -> ParsedQuery:
        text = raw_query.strip()
        if not text:
            return ParsedQuery(
                raw_query="",
                visual_prompt="",
                entities=[],
                folder_keywords=[],
                entity_ids=[],
                has_visual_scene=False
            )

        working = text

        # 1. Detect classification intent (real photo vs screenshot)
        classification = "ALL"
        if re.search(r"\b(screenshot|screenshots|screen\s*grab|screen\s*shot)\b", working, re.I):
            classification = "SCREENSHOT"
            working = re.sub(r"\b(screenshot|screenshots|screen\s*grab|screen\s*shot)s?\b", "", working, flags=re.I).strip()
        elif re.search(r"\b(photo|photos|picture|pictures|pic|pics|camera)\b", working, re.I):
            classification = "REAL_PHOTOS"
            working = re.sub(r"\b(photos?|pictures?|pics?|camera)\b", "", working, flags=re.I).strip()
        elif re.search(r"\b(all\s+files|everything|all\s+photos\s+and\s+screenshots)\b", working, re.I):
            classification = "ALL"
            working = re.sub(r"\b(all\s+files|everything|all\s+photos\s+and\s+screenshots)\b", "", working, flags=re.I).strip()

        # 2. Extract parenthetical entity annotations like "dobby(my dog)" or "charlie (pet cat)"
        entities: List[Dict[str, Any]] = []
        matched_entity_ids: List[int] = []
        folder_keywords: List[str] = []
        visual_replacements = {}

        paren_matches = re.finditer(r"(\b[a-zA-Z0-9_\-]{2,25})\s*\(([^)]+)\)", working)
        for m in paren_matches:
            ent_name = m.group(1).strip()
            ent_hint = m.group(2).strip()
            # Clean hint (e.g., "my dog" -> "dog")
            clean_type = re.sub(r"\b(my|our|a|the|pet)\b", "", ent_hint, flags=re.I).strip()
            entities.append({
                "name": ent_name,
                "type": clean_type or ent_hint
            })
            folder_keywords.append(ent_name.lower())
            if clean_type:
                visual_replacements[m.group(0)] = clean_type

        for orig, repl in visual_replacements.items():
            working = working.replace(orig, repl)

        # 3. Strip conversational command prefixes
        cleaned = working
        for pat in CONVERSATIONAL_PREFIXES:
            cleaned = re.sub(pat, "", cleaned, flags=re.I).strip()

        # 4. Extract temporal / date bounds
        date_from, date_to, date_label, temp_phrase = self._extract_date_range(cleaned)
        if temp_phrase:
            # Remove temporal phrase from the visual prompt string
            cleaned = re.sub(re.escape(temp_phrase), "", cleaned, flags=re.I).strip()

        # 5a. Check against tagged People & Pets from the database (entities table)
        for db_ent in self.known_entities:
            ent_name = str(db_ent.get("name", "")).strip()
            ent_id = db_ent.get("id")
            if not ent_name or len(ent_name) < 2:
                continue
            pattern = rf"\b{re.escape(ent_name)}(?:'s)?\b"
            if re.search(pattern, cleaned, re.I):
                ent_type_raw = str(db_ent.get("entity_type", "PERSON")).upper()
                ent_type_label = "pet" if ent_type_raw == "PET" else "person"
                if ent_id is not None and int(ent_id) not in matched_entity_ids:
                    matched_entity_ids.append(int(ent_id))
                if not any(str(e.get("name", "")).lower() == ent_name.lower() for e in entities):
                    ent_entry: Dict[str, Any] = {"name": ent_name, "type": ent_type_label}
                    if ent_id is not None:
                        ent_entry["id"] = int(ent_id)
                    entities.append(ent_entry)
                if ent_name.lower() in self.known_folders and ent_name.lower() not in folder_keywords:
                    folder_keywords.append(ent_name.lower())
                cleaned = re.sub(pattern, " ", cleaned, flags=re.I).strip()

        # 5b. Check against known entity aliases (e.g. dobby -> dog, puppy -> dog)
        for alias, visual_concept in self.entity_aliases.items():
            # Skip if already matched as a database entity
            if any(str(e.get("name", "")).lower() == alias.lower() for e in entities):
                continue
            if re.search(rf"\b{re.escape(alias)}\b", cleaned, re.I):
                if alias not in folder_keywords:
                    folder_keywords.append(alias)
                entities.append({"name": alias.capitalize(), "type": visual_concept})
                cleaned = re.sub(rf"\b{re.escape(alias)}\b", visual_concept, cleaned, flags=re.I)

        # 6. Check against known folder names (e.g. if library has folder "Dobby" or "Yellowstone")
        for kf in self.known_folders:
            if not kf or len(kf) < 3 or kf in ("pictures", "photos", "dcim", "camera", "desktop", "downloads"):
                continue
            # Look for whole-word occurrence
            if re.search(rf"\b{re.escape(kf)}\b", cleaned, re.I):
                if kf not in folder_keywords:
                    folder_keywords.append(kf)
                # If not already in entities, add as matched folder entity
                if not any(str(e.get("name", "")).lower() == kf for e in entities):
                    entities.append({"name": kf.capitalize(), "type": "folder"})

        # 7. Clean and construct the visual prompt for CLIP
        # Remove trailing/leading prepositions/conjunctions like "at", "in", "on", "from", "of", "and", "with" left behind
        visual_tokens = re.sub(r"\s+", " ", cleaned).strip()
        for _ in range(3):
            visual_tokens = re.sub(
                r"^(?:at|in|on|from|with|during|of|and|a|an|the|me|all|show|find)\b\s*",
                "",
                visual_tokens,
                flags=re.I
            ).strip()
            visual_tokens = re.sub(
                r"\s*\b(?:at|in|on|from|with|during|of|and|a|an|the)$",
                "",
                visual_tokens,
                flags=re.I
            ).strip()
        visual_tokens = re.sub(r"[!?,.]", "", visual_tokens).strip()

        has_visual_scene = bool(visual_tokens)

        # If visual tokens became empty, fall back to entity types (for non-DB aliases) or empty string for pure DB entity lookup
        if not visual_tokens:
            if entities and not matched_entity_ids:
                visual_tokens = " ".join(e.get("type", e["name"]) for e in entities)
            elif not entities:
                visual_tokens = text
                has_visual_scene = True

        return ParsedQuery(
            raw_query=raw_query,
            visual_prompt=visual_tokens,
            entities=entities,
            folder_keywords=folder_keywords,
            date_from=date_from,
            date_to=date_to,
            date_label=date_label,
            classification=classification,
            temporal_phrase=temp_phrase,
            entity_ids=matched_entity_ids,
            has_visual_scene=has_visual_scene
        )

    def _extract_date_range(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Parses relative or absolute date expressions in the text.
        Returns (date_from, date_to, date_label, matched_phrase).
        """
        ref = self.reference_date

        # Relative: "last month"
        m = re.search(r"\b(?:in\s+)?last\s+month\b", text, re.I)
        if m:
            first_of_curr = ref.replace(day=1)
            last_month_end = first_of_curr - relativedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            label = last_month_start.strftime("%B %Y")
            return (
                last_month_start.strftime("%Y-%m-%d"),
                last_month_end.strftime("%Y-%m-%d 23:59:59"),
                label,
                m.group(0)
            )

        # Relative: "this month"
        m = re.search(r"\b(?:in\s+)?this\s+month\b", text, re.I)
        if m:
            first_of_curr = ref.replace(day=1)
            next_month = first_of_curr + relativedelta(months=1)
            month_end = next_month - relativedelta(days=1)
            label = first_of_curr.strftime("%B %Y")
            return (
                first_of_curr.strftime("%Y-%m-%d"),
                month_end.strftime("%Y-%m-%d 23:59:59"),
                label,
                m.group(0)
            )

        # Relative: "last year"
        m = re.search(r"\b(?:in\s+)?last\s+year\b", text, re.I)
        if m:
            target_year = ref.year - 1
            return (
                f"{target_year}-01-01",
                f"{target_year}-12-31 23:59:59",
                str(target_year),
                m.group(0)
            )

        # Relative: "this year"
        m = re.search(r"\b(?:in\s+)?this\s+year\b", text, re.I)
        if m:
            return (
                f"{ref.year}-01-01",
                f"{ref.year}-12-31 23:59:59",
                str(ref.year),
                m.group(0)
            )

        # Relative: "last week"
        m = re.search(r"\b(?:in\s+)?last\s+week\b", text, re.I)
        if m:
            start_date = ref - relativedelta(weeks=1, days=ref.weekday())
            end_date = start_date + relativedelta(days=6)
            return (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d 23:59:59"),
                f"Week of {start_date.strftime('%b %d, %Y')}",
                m.group(0)
            )

        # Relative: "yesterday"
        m = re.search(r"\byesterday\b", text, re.I)
        if m:
            yest = ref - relativedelta(days=1)
            return (
                yest.strftime("%Y-%m-%d"),
                yest.strftime("%Y-%m-%d 23:59:59"),
                yest.strftime("%b %d, %Y"),
                m.group(0)
            )

        # Season + Year: e.g. "summer 2024", "in summer of 2023", "last summer"
        m = re.search(r"\b(?:in\s+)?(last\s+)?(spring|summer|fall|autumn|winter)(?:\s+of)?(?:\s+(\d{4}))?\b", text, re.I)
        if m:
            is_last = bool(m.group(1))
            season = m.group(2).lower()
            year_str = m.group(3)
            if year_str:
                target_year = int(year_str)
            elif is_last:
                target_year = ref.year if season in ("winter", "fall", "autumn") and ref.month < 6 else ref.year - 1
            else:
                target_year = ref.year

            start_m, end_m = SEASON_MONTHS[season]
            start_date = date(target_year, start_m, 1)
            if start_m <= end_m:
                end_date = (date(target_year, end_m, 1) + relativedelta(months=1)) - relativedelta(days=1)
            else:
                # Winter spans across year boundary
                end_date = (date(target_year + 1, end_m, 1) + relativedelta(months=1)) - relativedelta(days=1)

            label = f"{season.capitalize()} {target_year}"
            return (
                start_date.strftime("%Y-%m-%d"),
                end_date.strftime("%Y-%m-%d 23:59:59"),
                label,
                m.group(0)
            )

        # Specific Month + Year: e.g. "July 2024", "in March of 2022", "January 2025"
        for m_name, m_num in MONTH_NAMES.items():
            pattern = rf"\b(?:in\s+)?{m_name}(?:\s+of)?\s+(\d{{4}})\b"
            m = re.search(pattern, text, re.I)
            if m:
                target_year = int(m.group(1))
                start_d = date(target_year, m_num, 1)
                end_d = (start_d + relativedelta(months=1)) - relativedelta(days=1)
                label = f"{m_name.capitalize()} {target_year}"
                return (
                    start_d.strftime("%Y-%m-%d"),
                    end_d.strftime("%Y-%m-%d 23:59:59"),
                    label,
                    m.group(0)
                )

        # Month without year: e.g. "in August", "this past July"
        for m_name, m_num in MONTH_NAMES.items():
            pattern = rf"\b(?:in\s+|during\s+)?(?:this\s+past\s+|last\s+)?{m_name}\b"
            m = re.search(pattern, text, re.I)
            if m and not re.search(rf"{m_name}\s+\d{{4}}", text, re.I):
                target_year = ref.year if m_num <= ref.month else ref.year - 1
                start_d = date(target_year, m_num, 1)
                end_d = (start_d + relativedelta(months=1)) - relativedelta(days=1)
                label = f"{m_name.capitalize()} {target_year}"
                return (
                    start_d.strftime("%Y-%m-%d"),
                    end_d.strftime("%Y-%m-%d 23:59:59"),
                    label,
                    m.group(0)
                )

        # Standalone Year: e.g. "in 2024", "2023"
        m = re.search(r"\b(?:in\s+)?(19\d{2}|20\d{2})\b", text, re.I)
        if m:
            yr = int(m.group(1))
            if 1990 <= yr <= 2040:
                return (
                    f"{yr}-01-01",
                    f"{yr}-12-31 23:59:59",
                    str(yr),
                    m.group(0)
                )

        # "recent" or "recently" -> last 60 days
        m = re.search(r"\b(?:recently|recent\s+photos?)\b", text, re.I)
        if m:
            start_d = ref - relativedelta(days=60)
            return (
                start_d.strftime("%Y-%m-%d"),
                ref.strftime("%Y-%m-%d 23:59:59"),
                "Recent (Last 60 Days)",
                m.group(0)
            )

        return None, None, None, None
