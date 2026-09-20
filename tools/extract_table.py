#!/usr/bin/env python3

from ast import pattern
import json
import sys
import argparse
import re
from datetime import date

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

    def print(self):
        print(f"Page: {self.page}, Row: {self.row}, Qadi: {self.qadi}, Record Number: {self.record_number}, Subject: {self.subject}, Summary: {self.summary}, Jews Mentioned: {self.jews_mentioned}")

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
        record.print()

        
    def load_json(self):
        with open(self.json_file, 'r') as f:
            return json.load(f)

def main(argv=None):
    # ap = argparse.ArgumentParser(description='Extract table from JSON file')
    # ap.add_argument('json_file', help='Path to the JSON file')    
    # args = ap.parse_args(argv)
    # file_path = args.json_file
    file_name = "/home/danny/src/xpdf/data/out/24_Sicil_no.031.json"
    extractor = TableExtractor(file_name)
    
    extractor.extract()

if __name__ == '__main__':
    sys.exit(main())