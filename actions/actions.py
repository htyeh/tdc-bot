# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions


from typing import Any, Text, Dict, List, Union

from rasa_sdk import Action, Tracker
from rasa_sdk.events import AllSlotsReset
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormAction
from rasa_sdk.forms import FormValidationAction
from collections import defaultdict
from datetime import date
import pandas as pd

def create_country2code():
    with open('custom_data/country_list.txt') as file:
        return {line.split('|')[1].strip():line.split('|')[0].strip() for line in file}

def create_code2country():
    with open('custom_data/country_list.txt') as file:
        return {line.split('|')[0].strip():line.split('|')[1].strip() for line in file}

def create_visit_history(source):
    '''
    Returns:
        country2days (str -> int): country to total duration of stay
        country2firstvisit (str -> datetime.date): country to first visited date
        country2lastvisit (str -> datetime.date): country to last visited date
        visityear2countries (str -> list): year to countries visited in the year
    '''
    country2days = defaultdict(int)
    country2firstvisit = dict()
    country2lastvisit = dict()
    visityear2countries = defaultdict(list)

    df = pd.read_csv(source)
    entry_count = len(df)
    for i in range(entry_count):
        '''
        entry_date: date in the current line
        departure_date: entry_date of the following line
        delta: length of stay for country of the current line
        '''
        entry_y, entry_m, entry_d = df['DATE'][i].split('-')
        entry_date = date(int(entry_y), int(entry_m), int(entry_d))
        country = df['ENTERED'][i]
        try:
            depart_y, depart_m, depart_d = df['DATE'][i+1].split('-')
            departure_date = date(int(depart_y), int(depart_m), int(depart_d))
        except KeyError:
            depart_y = str(date.today().year)
            departure_date = date.today()
        delta = departure_date - entry_date
        country2days[country] += delta.days
        country2lastvisit[country] = departure_date
        if country not in country2firstvisit:
            country2firstvisit[country] = entry_date
        # use list instead of set to preserve order of visit for the report
        if country not in visityear2countries[entry_y]:
            visityear2countries[entry_y].append(country)
        if country not in visityear2countries[depart_y]:
            visityear2countries[depart_y].append(country)
    return country2days, country2firstvisit, country2lastvisit, visityear2countries

class TDCForm(FormAction):
    def name(self):
        return "TDC_form"

    @staticmethod
    def required_slots(tracker):
        res = ["track_home", "track_residency"]
        if tracker.get_slot("track_home") == True:
            res += ["home_name"]
        if tracker.get_slot("track_residency") == True:
            res += ["residency_name", "residency_begin"]
        return res

    def submit(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict]:
        return []

    def slot_mappings(self) -> Dict[Text, Union[Dict, List[Dict]]]:
        return {
            "track_home": [
                self.from_intent(intent="affirm", value=True),
                self.from_intent(intent="deny", value=False),
                self.from_intent(intent="inform", value=True),
            ],
            "home_name": [
                self.from_entity(entity="GPE"),
            ],
            "track_residency": [
                self.from_intent(intent="affirm", value=True),
                self.from_intent(intent="deny", value=False),
                self.from_intent(intent="inform", value=True),
            ],
            "residency_name": [
                self.from_entity(entity="GPE"),
            ],
            "residency_begin": [
                self.from_entity(entity="DATE"),
            ]
        }


# class ActionConfirmFormFilled(Action):

#     def name(self) -> Text:
#         return "action_confirm_form_filled"

#     def run(self, dispatcher: CollectingDispatcher,
#             tracker: Tracker,
#             domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

#         dispatcher.utter_message(text="OK, I have everything. Would you like me to show the results now?")

#         return []

class ActionAddRecord(Action):

    def name(self) -> Text:
        return "action_add_record"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        country2code = create_country2code()
        new_country = tracker.get_slot("new_country").title()
        new_country_code = country2code[new_country]
        new_date = tracker.get_slot("new_date")
        with open("travel_history.csv", "a") as log:
            log.write(",".join([new_date, new_country_code])+"\n")

        dispatcher.utter_message(text="OK, I added this record to the log.")

        return [AllSlotsReset()]

class ActionPrintResult(Action):

    def name(self) -> Text:
        return "action_print_result"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        country2days, country2firstvisit, country2lastvisit, visityear2countries = create_visit_history("travel_history.csv")
        num_visited_countries = len(country2days)
        country2code = create_country2code()
        code2country = create_code2country()

        msg = "Here are your results.\n\n"
        msg += "You have visited " + str(num_visited_countries) + " countries until today.\n\n"

        if tracker.get_slot("track_home"):
            home_country = tracker.get_slot("home_name").title()
            home_country_code = country2code[home_country]
            days_home = country2days[home_country_code]
            days_abroad = sum(days for country, days in country2days.items() if country != home_country_code)
            msg += "You have spent " + str(days_home) + " days home and " + str(days_abroad) + " days abroad.\n\n"
        if tracker.get_slot("track_residency"):
            residence_country = tracker.get_slot("residency_name").title()
            begin_date = tracker.get_slot("residency_begin")
            y, m, d = begin_date.split("-")
            residency_begin = date(int(y), int(m), int(d))
            delta = date.today()-residency_begin
            residency_length = delta.days
            msg += "You have been residing in " + residence_country + " for " + str(int(residency_length/365)) + " year(s) and " + str(residency_length%365) + " days.\n\n"
        msg += "This is how long you spent in each visited country:\n\n"
        for country, days in sorted(country2days.items(), key=lambda x:x[1], reverse=True):
            msg += "In " + code2country[country] + ": " + str(days) + " day(s).\n"

        dispatcher.utter_message(text=msg)

        return [AllSlotsReset()]

# class ActionDefaultFallback(Action):
#     """Ask user to repeat if default_fallback"""

#     def name(self) -> Text:
#         return "action_default_fallback"

#     def run(
#         self,
#         dispatcher: CollectingDispatcher,
#         tracker: Tracker,
#         domain: Dict[Text, Any],
#     ) -> List[Dict[Text, Any]]:
#         dispatcher.utter_message(text="Sorry, I didn't get that. Let's try again.")

#         return [UserUtteranceReverted()]