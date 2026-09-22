#!/usr/bin/env python3

from ast import pattern
import json
import sys
import argparse
import re
from datetime import date

import requests

class TransliteratedString:
    """An Arabic string and its Hebrew transliteration (taatik).

    The transliteration implements the Academy of the Hebrew Language
    rules for the simple (unpointed) Arabic-to-Hebrew transliteration:
    https://hebrew-academy.org.il/wp-content/uploads/taatik-arabic-ivrit-2025-1.pdf
    """

    # Consonants, per the paper's consonant table (העיצורים).
    # ك is written כ even at the end of a word (בית סוריכ).
    LETTER_MAP = {
        'أ': 'א', 'إ': 'א', 'ا': 'א', 'ٱ': 'א', 'آ': 'אא', 'ء': 'א', 'ى': 'א',
        'ب': 'ב', 'ت': 'ת', 'ث': 'ת׳', 'ج': 'ג׳',
        'ح': 'ח', 'خ': 'ח׳', 'د': 'ד', 'ذ': 'ד׳',
        'ر': 'ר', 'ز': 'ז', 'س': 'ס', 'ش': 'ש',
        'ص': 'ס׳', 'ض': 'ד', 'ط': 'ט', 'ظ': 'ז',
        'ع': 'ע', 'غ': 'ר׳', 'ف': 'פ', 'ق': 'ק', 'ك': 'כ',
        'ل': 'ל', 'م': 'מ', 'ن': 'נ', 'ه': 'ה',
        'و': 'ו', 'ي': 'י', 'ؤ': 'ו', 'ئ': 'י', 'ة': 'ה',
    }

    # Final letter forms at the end of a word
    FINAL_FORMS = {'מ': 'ם', 'נ': 'ן', 'פ': 'ף'}

    # Arabic-Indic (٠-٩) and Eastern Arabic-Indic (۰-۹) digits,
    # transliterated as 0-9
    DIGITS = {**{chr(0x0660 + i): str(i) for i in range(10)},
              **{chr(0x06f0 + i): str(i) for i in range(10)}}

    # Sun letters (אותיות שמש): the ל of the definite article assimilates
    SUN_LETTERS = set('تثدذرزسشصضطظلن')

    # Variants of the definite article
    ARTICLES = ('ال', 'ٱل', 'أل')

    # Arabic diacritics
    FATHA, DAMMA, KASRA = '\u064e', '\u064f', '\u0650'
    SUKUN, SHADDA = '\u0652', '\u0651'
    DAGGER_ALIF, MADDA_MARK = '\u0670', '\u0653'
    HARAKAT = set('\u064b\u064c\u064d\u064e\u064f\u0650')            # tanwin + short vowels
    OTHER_MARKS = set('\u0640\u0651\u0652\u0653\u0654\u0655\u0656\u0657\u0658')
    ALL_MARKS = HARAKAT | OTHER_MARKS

    def __init__(self, value):
        self.value = value
        self.transliterated = self.transliterate()

    def __repr__(self):
        return f"TransliteratedString(original={self.value!r}, transliterated={self.transliterated!r})"

    def transliterate(self):
        """Transliterate self.value from Arabic into Hebrew following the
        Academy of the Hebrew Language rules (the simple, unpointed form).
        The result is stored in self.transliterated and returned."""
        if not self.value:
            return None
        self.transliterated = self.transliterate_arabic(self.value)
        return self.transliterated

    @classmethod
    def transliterate_arabic(cls, text):
        """Transliterate an entire Arabic text, word by word, preserving
        whitespace and any non-Arabic characters."""
        return ''.join(
            cls._transliterate_word(part) if part and not part.isspace() else part
            for part in re.split(r'(\s+)', text)
        )

    @classmethod
    def _transliterate_word(cls, word):
        cleaned = ''.join(c for c in word if c not in cls.ALL_MARKS and c != cls.DAGGER_ALIF)

        # the word Allah is transliterated אללה
        if cleaned in ('الله', 'ﷲ'):
            return 'אללה'

        # The definite article (ال, ٱل, أل) is separated from the word by
        # a maqaf (אל־בירה); before sun letters the ל is not written and
        # the א is maqaf'd instead (א־שמאלייה).
        prefix = ''
        letters = []  # (letter, index) of the first three Arabic letters
        idx = 0
        while idx < len(word) and len(letters) < 3:
            if word[idx] in cls.ALL_MARKS or word[idx] == cls.DAGGER_ALIF:
                idx += 1
                continue
            letters.append((word[idx], idx))
            idx += 1
        if len(letters) == 3 and ''.join(l for l, _ in letters[:2]) in cls.ARTICLES:
            prefix = 'א־' if letters[2][0] in cls.SUN_LETTERS else 'אל־'
            word = word[letters[2][1]:]

        hebrew = []
        prev_letter = None   # the last Arabic letter processed
        prev_mark = None     # the diacritic attached to it

        i = 0
        while i < len(word):
            ch = word[i]

            if ch == cls.DAGGER_ALIF:
                # an alef written above a letter is written as א after it
                hebrew.append('א')
                i += 1
                continue
            if ch == cls.MADDA_MARK:
                # an alef with madda is written as two alefs
                hebrew.append('א')
                i += 1
                continue
            if ch in cls.HARAKAT:
                # short u / i are written as ו / י (מוחמד, ג'יסר), except
                # on an alef (אבראהים), when a ו / י letter that follows
                # already represents the vowel (שריף, מחמוד, מוסא) or a
                # shva-hamza seat covers it (ביר, בוס), and as the
                # harakah of a consonantal ו / י; fatha and tanwin are
                # not marked
                # find the next letter after this harakah (skipping marks)
                j = i + 1
                while j < len(word) and word[j] in cls.ALL_MARKS:
                    j += 1
                after = word[j] if j < len(word) else ''
                after2 = word[j + 1] if j + 1 < len(word) else ''
                covered = after in ('و', 'ي') \
                    or (after in ('ؤ', 'ئ') and after2 not in cls.HARAKAT)
                if ch == cls.DAMMA and prev_letter not in ('و', 'ي', 'ؤ') \
                        and not covered:
                    hebrew.append('ו')
                elif ch == cls.KASRA and prev_letter not in ('ي', 'ئ') \
                        and prev_letter not in ('أ', 'إ', 'ا', 'آ', 'ٱ') \
                        and not covered:
                    hebrew.append('י')
                prev_mark = ch
                i += 1
                continue
            if ch in cls.OTHER_MARKS:  # shadda, sukun, tatweel, hamza marks
                prev_mark = ch
                i += 1
                continue

            nxt = word[i + 1] if i + 1 < len(word) else ''

            if ch == 'ة':
                # ta marbuta: ה at the end of a word, ת in construct state
                after = next((c for c in word[i + 1:] if c not in cls.ALL_MARKS), None)
                hebrew.append('ה' if after is None or after not in cls.LETTER_MAP else 'ת')
            elif ch in ('ؤ', 'ئ'):
                # hamza on a waw/yod seat: written as ו / י when it carries
                # no vowel (בוס, ביר), and as א when it carries one
                # (מואייד, ואאל)
                hebrew.append('א' if nxt in cls.HARAKAT else cls.LETTER_MAP[ch])
            elif ch in ('و', 'ي'):
                # A waw/yod is consonantal if it follows an alef (which
                # is never followed by a long vowel), if it follows a
                # fatha (the aw/ay diphthong), or if it carries a
                # harakah, sukun or shadda.
                consonantal = (prev_letter in ('ا', 'آ')
                              or prev_mark == cls.FATHA
                              or nxt in cls.HARAKAT
                              or nxt == cls.SUKUN
                              or nxt == cls.SHADDA)
                # Per note 5 a consonantal waw/yod is doubled when it
                # follows a vowel sound (מועאווייה, טייבה, עווד), but not
                # when it opens a syllable (עריאן, ואאל).
                after_vowel = (prev_letter in ('ا', 'آ')
                              or prev_mark in cls.HARAKAT)
                letter = cls.LETTER_MAP[ch]
                hebrew.append(letter * 2 if (consonantal and after_vowel) else letter)
            elif ch in cls.DIGITS:
                # Arabic-Indic digits are transliterated as 0-9 (١٢٥ -> 125)
                hebrew.append(cls.DIGITS[ch])
            elif ch in cls.LETTER_MAP:
                hebrew.append(cls.LETTER_MAP[ch])
            else:
                # non-Arabic characters (Latin letters, punctuation,
                # Western digits) are passed through unchanged
                hebrew.append(ch)

            prev_letter = ch
            prev_mark = None
            i += 1

        result = ''.join(hebrew)

        # final letter forms (ף, ם, ן) at the end of the word, skipping
        # any trailing non-letter characters
        for j in range(len(result) - 1, -1, -1):
            if result[j] in cls.FINAL_FORMS:
                result = result[:j] + cls.FINAL_FORMS[result[j]] + result[j + 1:]
                break
            if 'א' <= result[j] <= 'ת':
                break

        return prefix + result
        
class Person:
    def __init__(self, name: TransliteratedString, role):
        self.name = name        
        self.role = role

    def __repr__(self):
        return f"Person(name={self.name!r}, role={self.role!r})"
                
class SijilRecord:
    def __init__(self, page: int, row: int, qadi: str, record_number: str, subject: str, summary: str):
        self.page = page
        self.row = row
        self.qadi =  TransliteratedString(qadi)
        self.record_number = record_number
        self.subject = subject
        self.summary = summary        
        self.jews_mentioned = self.extract_jews()
        self.date = self.extract_date()
        self.hebrew_description = None
        self.hebrew_summary = None
        self.hebrew_subject = None
        self.hebrew_subject_short = None
        self.persons = list[Person]()
        self.places = list[TransliteratedString]()
        
    def extract_date(self):
        pattern = r'([٠-٩0-9]{4})/([٠-٩0-9]{1,2})/([٠-٩0-9]{1,2})'
        
        extracted_dates = []
    
        for match in re.finditer(pattern, self.record_number):
            year_str, month_str, day_str = match.groups()
            
            # Python's built-in int() automatically converts Eastern Arabic numerals (١,٢,٣) to standard integers (1,2,3)
            year = int(year_str)
            month = int(month_str)
            day = int(day_str)
            
            try:
                gregorian_date = date(year, month, day)
                extracted_dates.append(gregorian_date)
            except ValueError:
                # Skip invalid dates (e.g., February 31st)
                continue
                
        if len(extracted_dates) == 0:
            return None
        elif len(extracted_dates) == 1:
            return extracted_dates[0]
        else:
            print(f"Warning: Multiple dates found in text '{self.record_number}'. Using the first one.")
            return extracted_dates[0]

    def extract_jews(self):
        mention_jews = re.search(r'يهود', self.summary) or re.search(r'يهود', self.subject)
        return bool(mention_jews)

    def translate(self):
        date_str = "between the 15th and the 18th centuries"
        if self.date:
            date_str = self.date.strftime("%Y-%m-%d")
                
        self.hebrew_subject = self.translate_subject(date_str)
        print(self.hebrew_subject)
        self.hebrew_summary = self.translate_summary(date_str)
        print(self.hebrew_summary)
        self.hebrew_description = self.get_hebrew_description(date_str)
        print(self.hebrew_description)
        self.hebrew_subject_short = self.get_hebrew_subject(date_str)
        print(self.hebrew_subject_short)
        self.persons = self.extract_persons(date_str)
        print(self.persons)
        self.places = self.extract_places(date_str)
        print(self.places)
        

    def translate_summary(self,date_str):
        if not self.summary:
            return ""
        prompt = f"Following is a record summary from the Ottoman Sharia Court in Jerusalem from {date_str}. Provide direct translation of the Arabic text to Hebrew. Write only the Translation and nothing else: '{self.summary}'"
               
        return self.call_ollama(prompt)
    
    def translate_subject(self,date_str):
        if not self.subject:
            return ""
        prompt = f"Following is a record subject from the Ottoman Sharia Court in Jerusalem from {date_str}. Provide direct translation of the Arabic text to Hebrew. Write only the Translation and nothing else: '{self.subject}'"
        
        return self.call_ollama(prompt)
    
    def extract_persons(self, date_str):        
        prompt = 'Following is a record summary from the Ottoman Sharia Court in Jerusalem from '+date_str+'. Extract all persons names and roles in the following json format: [{"name":"محمد أفندي بن إبراهيم", "role":"seller"},...]. Keep the exact original Arabic name and spelling. The record is: '
        prompt += f"qadi: {self.qadi}, subject: '{self.subject}', summary: '{self.summary}'"
        persons_json = self.call_ollama_json(prompt)

        persons = []
        if isinstance(persons_json, list):
            for p in persons_json:
                name = TransliteratedString(p.get('name'))
                name.transliterate()
                person = Person(name, p.get('role'))
                person.transliterated_name = name.transliterated
                persons.append(person)
        return persons

    def extract_places(self, date_str):        
        prompt = 'Following is a record summary from the Ottoman Sharia Court in Jerusalem from '+date_str+'. Extract all places mentioned in the record in the following json format: [{"place":"بيت صفافا"},...]. Keep the exact original Arabic name and spelling. The record is: '
        prompt += f"qadi: {self.qadi}, subject: '{self.subject}', summary: '{self.summary}'"
        places_json = self.call_ollama_json(prompt)

        places = []
        if isinstance(places_json, list):
            for p in places_json:
                place = TransliteratedString(p.get('place'))
                place.transliterate()
                places.append(place)
        return places

    def get_hebrew_description(self,date_str):
        prompt = f'Following is a record summary from the Ottoman Sharia Court in Jerusalem from {date_str}. Provide up to 10 words summary of this record, in Hebrew. The record is: '
        prompt += f"qadi: {self.qadi}, subject: '{self.subject}', summary: '{self.summary}'"
        return self.call_ollama(prompt)

    def get_hebrew_subject(self,date_str):
        prompt = f'Following is a record summary from the Ottoman Sharia Court in Jerusalem from {date_str}. What is the subject? write in Hebrew, one or two words. The record is: '
        prompt += f"qadi: {self.qadi}, subject: '{self.subject}', summary: '{self.summary}'"
        return self.call_ollama(prompt)
    
    
    def call_ollama(self, prompt):
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "translategemma:4b",
            "prompt": prompt,
            "stream": False
        }

        print(f"Calling Ollama with prompt: {prompt}")
        response = requests.post(url, json=payload)
        return response.json()['response']

    def _try_parse_json(self, text):
        """Try to parse a JSON object out of the model's response.
        Returns (obj, None) on success, or (None, error_message) on failure."""
        # Strip markdown code fences the model may wrap the JSON in,
        # e.g. ```json ... ```
        cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip()).strip()
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()

        try:
            return json.loads(cleaned), None
        except json.JSONDecodeError as e:
            # Fall back to extracting the first JSON object or array
            # in case the model added extra text around it
            match = re.search(r'[\[{].*[\]}]', cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0)), None
                except json.JSONDecodeError:
                    pass
            return None, str(e)

    def call_ollama_json(self, prompt, max_retries=3):
        current_prompt = prompt
        last_response = None

        for attempt in range(1, max_retries + 1):
            response = self.call_ollama(current_prompt)
            last_response = response

            # An empty response means there are no results - return an
            # empty JSON object instead of an empty string
            if not response or not response.strip():
                return {}

            obj, error = self._try_parse_json(response)
            if error is None:
                return obj

            if attempt < max_retries:
                print(f"Invalid JSON from Ollama (attempt {attempt}/{max_retries}): {error}")
                current_prompt = (
                    f"{prompt}\n\n"
                    f"Your previous response was not valid JSON: '{response}'\n"
                    f"The error was: {error}\n"
                    "Please respond with only valid JSON and nothing else. "
                    "If there are no results, return an empty JSON object '{}'."
                )

        raise ValueError(f"Ollama did not return valid JSON after {max_retries} attempts: {last_response}")
    
    def print(self):
        # prints as CSV:
        print(f"{self.page}\t{self.row}\t{self.qadi.value}\t{self.record_number}\t{self.subject}\t{self.summary}\t{self.jews_mentioned}\t{self.date}")

class TableExtractor:
    def __init__(self, json_file):
        self.json_file = json_file

    def extract(self):
        doc = self.load_json()
        for page in doc:
            num = page["page"]
            for paragraph in page["paragraphs"]:
                type = paragraph["type"]
                if type == "table":                    
                    for row in paragraph["rows"]:
                        cells = row["cells"]
                        row_num = row["row"]                        
                        if len(cells) ==9:
                            if row_num == 2: # header row
                                continue
                            self.add_sigil_row(num, int(row_num/2), cells)
                            
                            
    def clean_up_text(self,text):
        # Remove leading/trailing whitespace and replace multiple spaces with a single space
        clean_text = re.sub(r'[\u202A-\u202C\u200E\u200F]', '', text)
        return ' '.join(clean_text.strip().split())    

    def add_sigil_row(self, page,row, cells):        
        summary = self.clean_up_text(cells[1]["text"])
        subject = self.clean_up_text(cells[3]["text"])
        record_number = self.clean_up_text(cells[5]["text"])
        qadi = self.clean_up_text(cells[7]["text"])
        
        record = SijilRecord(page, row, qadi, record_number, subject, summary)
        # if record.jews_mentioned:
        #     record.translate()
        record.print()
        
    def load_json(self):
        with open(self.json_file, 'r') as f:
            return json.load(f)

def main(argv=None):
    ap = argparse.ArgumentParser(description='Extract table from JSON file')
    ap.add_argument('json_file', help='Path to the JSON file')    
    args = ap.parse_args(argv)
    file_path = args.json_file    
    #file_path = "/home/danny/src/xpdf/data/out/01_Sicil_no.107.json"
    extractor = TableExtractor(file_path)
    
    extractor.extract()

if __name__ == '__main__':
    sys.exit(main())