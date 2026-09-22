#!/usr/bin/env python3

from ast import pattern
import json
import sys
import argparse
import re
from datetime import date

import requests

class SijilRecord:
    def __init__(self, page, row, qadi, record_number, subject, summary):
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
        self.persons = None # change to []
        self.places = None # change to []
        
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
        return self.call_ollama(prompt)

    def extract_places(self, date_str):        
        prompt = 'Following is a record summary from the Ottoman Sharia Court in Jerusalem from '+date_str+'. Extract all places mentioned in the record in the following json format: [{"place":"بيت صفافا"},...]. Keep the exact original Arabic name and spelling. The record is: '
        prompt += f"qadi: {self.qadi}, subject: '{self.subject}', summary: '{self.summary}'"
        return self.call_ollama(prompt)

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