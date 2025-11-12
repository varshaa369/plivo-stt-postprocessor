import re
from typing import List
from rapidfuzz import process, fuzz

# ==================== EMAIL FIXES ====================

def fix_email_spacing(text: str) -> str:
    """
    Fix common email spacing issues:
    - 'g mail.com' -> 'gmail.com'
    - 'gmailcom' -> 'gmail.com' (missing dot)
    - 'yahooo.com' -> 'yahoo.com' (typo)
    """
    # Pattern 1: Fix spaces in email domains (e.g., "g mail.com" -> "gmail.com")
    text = re.sub(r'(\w+)\s+mail\s*\.\s*com', r'\1mail.com', text, flags=re.IGNORECASE)
    
    # Pattern 2: Fix missing dot before domain extension (e.g., "gmailcom" -> "gmail.com")
    text = re.sub(r'@(\w+)(com|org|in|net)\b', r'@\1.\2', text, flags=re.IGNORECASE)
    
    # Pattern 3: Fix common typos
    typo_map = {
        'yahooo': 'yahoo',
        'gmial': 'gmail',
        'outlok': 'outlook',
    }
    for typo, correct in typo_map.items():
        text = re.sub(rf'\b{typo}\b', correct, text, flags=re.IGNORECASE)
    
    # Pattern 4: Remove spaces around @ and . in email contexts
    # Find email-like patterns and remove spaces
    def clean_email(match):
        email = match.group(0)
        email = re.sub(r'\s+', '', email)  # Remove all spaces
        email = re.sub(r'\.{2,}', '.', email)  # Fix multiple dots
        return email
    
    # Match email patterns with potential spacing issues
    text = re.sub(
        r'\b[\w\.-]+\s*@\s*[\w\s\.-]+\.\s*(?:com|org|in|net)\b',
        clean_email,
        text,
        flags=re.IGNORECASE
    )
    
    return text

EMAIL_TOKEN_PATTERNS = [
    (r'\b\(?(at|@)\)?\b', '@'),
    (r'\b(dot)\b', '.'),
    (r'\s*@\s*', '@'),
    (r'\s*\.\s*', '.')
]

def collapse_spelled_letters(s: str) -> str:
    """Collapse sequences like 'g m a i l' -> 'gmail'"""
    tokens = s.split()
    out = []
    i = 0
    while i < len(tokens):
        # lookahead for sequences of single letters
        if i+4 < len(tokens) and all(len(t)==1 for t in tokens[i:i+5]):
            out.append(''.join(tokens[i:i+5]))
            i += 5
        else:
            out.append(tokens[i])
            i += 1
    return ' '.join(out)

def normalize_email_tokens(s: str) -> str:
    s2 = s
    s2 = collapse_spelled_letters(s2)
    for pat, rep in EMAIL_TOKEN_PATTERNS:
        s2 = re.sub(pat, rep, s2, flags=re.IGNORECASE)
    s2 = fix_email_spacing(s2)
    return s2

# ==================== NUMBER HANDLING ====================

NUM_WORD = {
    'zero':'0','oh':'0','one':'1','two':'2','three':'3','four':'4','five':'5',
    'six':'6','seven':'7','eight':'8','nine':'9'
}

def words_to_digits(seq: List[str]) -> str:
    """Convert spoken numbers to digits, handling 'double nine' etc."""
    out = []
    i = 0
    while i < len(seq):
        tok = seq[i].lower()
        if tok in ('double','triple') and i+1 < len(seq):
            times = 2 if tok=='double' else 3
            nxt = seq[i+1].lower()
            if nxt in NUM_WORD:
                out.append(NUM_WORD[nxt]*times)
                i += 2
                continue
        if tok in NUM_WORD:
            out.append(NUM_WORD[tok])
            i += 1
        else:
            i += 1
    return ''.join(out)

def normalize_numbers_spoken(s: str) -> str:
    """Replace simple spoken digit sequences with digits"""
    tokens = s.split()
    out = []
    i = 0
    while i < len(tokens):
        # Check for number words in a small window
        window = []
        j = i
        while j < len(tokens) and j < i+8:
            if tokens[j].lower() in NUM_WORD or tokens[j].lower() in ('double', 'triple'):
                window.append(tokens[j])
                j += 1
            else:
                break
        
        if len(window) >= 1:
            wd = words_to_digits(window)
            if len(wd) >= 1:
                out.append(wd)
                i = j
                continue
        
        out.append(tokens[i])
        i += 1
    return ' '.join(out)

def normalize_currency(s: str) -> str:
    """
    Fix currency formatting:
    - 'rs' -> '₹'
    - 'rupees' -> '₹'
    - Add proper Indian comma grouping
    """
    # Replace 'rs' or 'rupees' with rupee symbol
    s = re.sub(r'\brs\s+', '₹', s, flags=re.IGNORECASE)
    s = re.sub(r'\brupees\s+', '₹', s, flags=re.IGNORECASE)
    
    # Ensure proper formatting: ₹ followed by number
    def indian_group(num_str):
        """Format number with Indian grouping (last 3, then every 2)"""
        num_str = re.sub('[^0-9]', '', num_str)
        if not num_str or len(num_str) <= 3:
            return num_str
        
        x = num_str
        last3 = x[-3:]
        rest = x[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        return ','.join(parts + [last3])
    
    def repl(m):
        raw = re.sub('[^0-9]', '', m.group(0))
        if not raw:
            return m.group(0)
        return '₹' + indian_group(raw)
    
    # Fix existing ₹ with numbers
    s = re.sub(r'₹\s*[0-9][0-9,\.]*', repl, s)
    
    return s

# ==================== TEXT NORMALIZATION ====================

def normalize_text(s: str) -> str:
    """
    Fix common speech-to-text errors:
    - Capitalization
    - Common abbreviations (pls, u, im)
    - Spelling errors
    """
    # Common abbreviation expansions
    replacements = {
        r'\bpls\b': 'please',
        r'\bu\b': 'you',
        r'\bur\b': 'your',
        r'\bim\b': "I'm",
        r'\badress\b': 'address',
        r'\bofer\b': 'offer',
        r'\bofering\b': 'offering',
        r'\blets\b': "let's",
    }
    
    for pattern, replacement in replacements.items():
        s = re.sub(pattern, replacement, s, flags=re.IGNORECASE)
    
    # Capitalize first letter of sentence
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    
    # Fix 'counteroffer' -> 'Counter-offer'
    s = re.sub(r'\bcounteroffer\b', 'Counter-offer', s, flags=re.IGNORECASE)
    s = re.sub(r'\bcounter offer\b', 'Counter-offer', s, flags=re.IGNORECASE)
    
    return s

def add_punctuation(s: str) -> str:
    """Add basic punctuation: commas after greetings, period at end"""
    # Add comma after name at start (e.g., "Ansh please" -> "Ansh, please")
    # Match capitalized word at start followed by lowercase word
    s = re.sub(r'^([A-Z][a-z]+)\s+([a-z])', r'\1, \2', s)
    
    # Add period at end if missing
    if s and s[-1] not in '.!?':
        s += '.'
    
    # Fix space before punctuation
    s = re.sub(r'\s+([.,!?])', r'\1', s)
    
    return s

def correct_names_with_lexicon(s: str, names_lex: List[str], threshold: int = 85) -> str:
    """
    Correct names using fuzzy matching against lexicon.
    Lower threshold from 90 to 85 for better recall.
    """
    tokens = s.split()
    out = []
    for t in tokens:
        # Only check tokens that look like they could be names (start with capital or all lowercase)
        if len(t) > 2 and (t[0].isupper() or t.islower()):
            best = process.extractOne(t, names_lex, scorer=fuzz.ratio)
            if best and best[1] >= threshold:
                out.append(best[0])
            else:
                # Capitalize if it looks like a name (at start or after comma)
                if len(out) == 0 or (len(out) > 0 and out[-1].endswith(',')):
                    out.append(t.capitalize())
                else:
                    out.append(t)
        else:
            out.append(t)
    return ' '.join(out)

# ==================== CANDIDATE GENERATION ====================

def generate_candidates(text: str, names_lex: List[str]) -> List[str]:
    """
    Generate candidate corrections. 
    OPTIMIZATION: Limit to 3 best candidates for speed.
    """
    cands = set()
    
    # Candidate 1: Full pipeline
    t1 = text
    t1 = normalize_text(t1)
    t1 = normalize_email_tokens(t1)
    t1 = normalize_numbers_spoken(t1)
    t1 = normalize_currency(t1)
    t1 = correct_names_with_lexicon(t1, names_lex)
    t1 = add_punctuation(t1)
    cands.add(t1)
    
    # Candidate 2: Email + punctuation focus
    t2 = text
    t2 = normalize_text(t2)
    t2 = normalize_email_tokens(t2)
    t2 = add_punctuation(t2)
    cands.add(t2)
    
    # Candidate 3: Original with minimal fixes
    t3 = text
    t3 = normalize_text(t3)
    t3 = fix_email_spacing(t3)
    t3 = add_punctuation(t3)
    cands.add(t3)
    
    # Deduplicate and limit to 3 for speed
    out = list(cands)
    # Sort by length (prefer complete transformations)
    out = sorted(out, key=lambda x: -len(x))[:3]
    
    return out