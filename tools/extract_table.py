#!/usr/bin/env python3

from ast import pattern
import json
import sys
import argparse
import re
from datetime import date

import requests

class TransliteratedString:
    def __init__(self, original, transliterated):
        self.original = original
        self.transliterated = transliterated

    def __repr__(self):
        return f"TransliteratedString(original={self.original!r}, transliterated={self.transliterated!r})"
        
class Person:
    def __init__(self, name: TransliteratedString, role):
        self.name = name
        self.transliterated_name = None
        self.role = role

    def __repr__(self):
        return f"Person(name={self.name!r}, role={self.role!r})"
                
class SijilRecord:
    def __init__(self, page: int, row: int, qadi: str, record_number: str, subject: str, summary: str):
        self.page = page
        self.row = row
        self.qadi = qadi
        self.record_number = record_number
        self.subject = subject
        self.summary = summary        
        self.jews_mentioned = self.extract_jews()
        self.date = self.extract_date()
        self.hebrew_description = None
        self.hebrew_summary = None
        self.hebrew_subject = None
        self.hebrew_subject_short = None
        self.persons = []
        self.places = []
        
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
                # transliteration is filled in later by a separate algorithm
                name = TransliteratedString(p.get('name'), None)
                persons.append(Person(name, p.get('role')))
        return persons

    def extract_places(self, date_str):        
        prompt = 'Following is a record summary from the Ottoman Sharia Court in Jerusalem from '+date_str+'. Extract all places mentioned in the record in the following json format: [{"place":"بيت صفافا"},...]. Keep the exact original Arabic name and spelling. The record is: '
        prompt += f"qadi: {self.qadi}, subject: '{self.subject}', summary: '{self.summary}'"
        places_json = self.call_ollama_json(prompt)

        places = []
        if isinstance(places_json, list):
            for p in places_json:
                # transliteration is filled in later by a separate algorithm
                places.append(TransliteratedString(p.get('place'), None))
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
        print(f"{self.page}\t{self.row}\t{self.qadi}\t{self.record_number}\t{self.subject}\t{self.summary}\t{self.jews_mentioned}\t{self.date}")

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
        record.translate()
        record.print()

        
    def load_json(self):
        with open(self.json_file, 'r') as f:
            return json.load(f)

def main(argv=None):
    # ap = argparse.ArgumentParser(description='Extract table from JSON file')
    # ap.add_argument('json_file', help='Path to the JSON file')    
    # args = ap.parse_args(argv)
    # file_path = args.json_file    
    file_path = "/home/danny/src/xpdf/data/out/01_Sicil_no.107.json"
    extractor = TableExtractor(file_path)
    
    extractor.extract()

if __name__ == '__main__':
    sys.exit(main())