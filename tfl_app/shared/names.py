from __future__ import annotations

import re

import pandas as pd


_RE_NONWORD = re.compile(r"[^\w]+", flags=re.UNICODE)
_RE_WHITESPACE = re.compile(r"\s+")
_RE_PARENS = re.compile(r"\([^)]*\)")
_TITLE_WORDS = {"MR", "MRS", "MS", "MISS", "DR", "HON", "JR", "SR", "II", "III", "IV"}
_RE_TITLE_WORDS = re.compile(r"\b(" + "|".join(_TITLE_WORDS) + r")\b\.?", re.IGNORECASE)
_NICKNAME_MAP = {
    "CHUCK": {"CHARLES"},
    "CHARLIE": {"CHARLES"},
    "CHARLES": {"CHUCK", "CHARLIE"},
}


def norm_name(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).replace("\u00A0", " ").strip().upper()
    return _RE_NONWORD.sub("", text)


def norm_name_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.replace("\u00A0", " ", regex=False)
        .str.strip()
        .str.upper()
        .str.replace(_RE_NONWORD, "", regex=True)
    )


def clean_filer_name_series(series: pd.Series) -> pd.Series:
    cleaned = series.fillna("").astype(str)
    cleaned = cleaned.str.replace(_RE_PARENS, "", regex=True)
    cleaned = cleaned.str.replace(_RE_TITLE_WORDS, "", regex=True)
    cleaned = cleaned.str.replace(_RE_WHITESPACE, " ", regex=True).str.strip()
    return cleaned


def clean_person_name(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    text = str(name).replace("\u00A0", " ").strip()
    if not text:
        return ""
    text = _RE_PARENS.sub("", text)
    text = _RE_TITLE_WORDS.sub("", text)
    text = _RE_WHITESPACE.sub(" ", text).strip()
    return text


def last_name_norm_from_text(text: str) -> str:
    if not text:
        return ""
    value = str(text).replace("\u00A0", " ").strip()
    if not value:
        return ""
    if "," in value:
        last = value.split(",", 1)[0].strip()
    else:
        parts = value.split()
        last = parts[-1] if parts else ""
    return norm_name(last)


def last_name_norm_series(series: pd.Series) -> pd.Series:
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0] if series.shape[1] > 0 else pd.Series([], dtype="string")
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    series = (
        series.fillna("")
        .astype("string")
        .str.replace("\u00A0", " ", regex=False)
        .str.strip()
    )
    comma_mask = series.str.contains(",", na=False)
    last_from_comma = (
        series.where(comma_mask, "")
        .astype("string")
        .str.split(",", n=1)
        .str[0]
        .astype("string")
        .str.strip()
    )
    last_from_space = (
        series.where(~comma_mask, "")
        .astype("string")
        .str.split()
        .str[-1]
        .fillna("")
        .astype("string")
        .str.strip()
    )
    last = last_from_comma.where(comma_mask, last_from_space).fillna("")
    return norm_name_series(last)


def first_name_norm_series(series: pd.Series) -> pd.Series:
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0] if series.shape[1] > 0 else pd.Series([], dtype="string")
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    series = (
        series.fillna("")
        .astype("string")
        .str.replace("\u00A0", " ", regex=False)
        .str.strip()
    )
    comma_mask = series.str.contains(",", na=False)
    first_from_comma = (
        series.where(comma_mask, "")
        .astype("string")
        .str.split(",", n=1)
        .str[1]
        .fillna("")
        .astype("string")
        .str.strip()
        .str.split()
        .str[0]
        .fillna("")
        .astype("string")
        .str.strip()
    )
    first_from_space = (
        series.where(~comma_mask, "")
        .astype("string")
        .str.split()
        .str[0]
        .fillna("")
        .astype("string")
        .str.strip()
    )
    first = first_from_comma.where(comma_mask, first_from_space).fillna("")
    return norm_name_series(first)


def last_first_initial_key(name: str) -> str:
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    text = str(name).replace("\u00A0", " ").strip()
    if not text:
        return ""
    if "," in text:
        last, rest = [part.strip() for part in text.split(",", 1)]
        first = rest
    else:
        tokens = text.split()
        if len(tokens) < 2:
            return ""
        first, last = tokens[0], tokens[-1]
    initial = ""
    for char in first:
        if char.isalnum():
            initial = char
            break
    if not last or not initial:
        return ""
    return norm_name(f"{last} {initial}")


def norm_person_variants(user_text: str) -> set[str]:
    if not user_text:
        return set()
    text = clean_person_name(user_text)
    if not text:
        return set()
    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
    else:
        tokens = text.split()
        if len(tokens) == 1:
            first, last = "", tokens[0]
        else:
            first, last = tokens[0], tokens[-1]
    variants = {norm_name(text)}
    raw_norm = norm_name(user_text)
    if raw_norm:
        variants.add(raw_norm)
    if first and last:
        variants |= {
            norm_name(f"{first} {last}"),
            norm_name(f"{last}, {first}"),
            norm_name(f"{last} {first}"),
            norm_name(f"{first}{last}"),
            norm_name(f"{last}{first}"),
        }
    return {variant for variant in variants if variant}


def _nickname_variants(first_norm: str) -> set[str]:
    if not first_norm:
        return set()
    variants = {first_norm}
    if first_norm in _NICKNAME_MAP:
        variants |= _NICKNAME_MAP[first_norm]
    for base, nicknames in _NICKNAME_MAP.items():
        if first_norm in nicknames:
            variants.add(base)
            variants |= nicknames
    return {variant for variant in variants if variant}


def norm_person_variants_with_nicknames(user_text: str) -> set[str]:
    variants = norm_person_variants(user_text)
    if not user_text:
        return variants
    text = clean_person_name(user_text)
    if not text:
        return variants

    def add_nickname_variants(first_value: str, last_value: str) -> None:
        first_norm = norm_name(first_value)
        last_norm = norm_name(last_value)
        if not first_norm or not last_norm:
            return
        for nickname in _nickname_variants(first_norm):
            if nickname == first_norm:
                continue
            variants.add(f"{nickname}{last_norm}")
            variants.add(f"{last_norm}{nickname}")

    if "," in text:
        parts = [part.strip() for part in text.split(",", 1)]
        last = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        first = rest.split()[0].strip() if rest else ""
        add_nickname_variants(first, last)
    else:
        tokens = text.split()
        if len(tokens) < 2:
            return variants
        first, last = tokens[0], tokens[-1]
        add_nickname_variants(first, last)
        if len(tokens) == 2:
            add_nickname_variants(last, first)
    return {variant for variant in variants if variant}


def parse_member_name(member_name: str) -> dict[str, str]:
    text = clean_person_name(member_name)
    if not text:
        return {"full_norm": "", "last_norm": "", "first_norm": "", "first_initial": "", "initial_key": ""}
    if "," in text:
        last, rest = [part.strip() for part in text.split(",", 1)]
        first = rest.split()[0].strip() if rest else ""
    else:
        tokens = text.split()
        if len(tokens) == 1:
            first, last = "", tokens[0]
        else:
            first, last = tokens[0], tokens[-1]
    first_norm = norm_name(first)
    last_norm = norm_name(last)
    first_initial = norm_name(first[0]) if first else ""
    initial_key = last_first_initial_key(text)
    return {
        "full_norm": norm_name(text),
        "last_norm": last_norm,
        "first_norm": first_norm,
        "first_initial": first_initial,
        "initial_key": initial_key,
    }


def parse_person_name(person_name: str) -> dict[str, str]:
    return parse_member_name(person_name)


_last_first_initial_key = last_first_initial_key
