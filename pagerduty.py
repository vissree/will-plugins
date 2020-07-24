from will import settings
from will.plugin import WillPlugin
from will.decorators import respond_to, require_settings

from datetime import datetime
from datetime import timedelta
import requests

class Pagerduty(object):

    def __init__(self, api_token):
        self.api_token = api_token
        self.url = "https://api.pagerduty.com"
        self.headers = { "Accept": "application/vnd.pagerduty+json;version=2",
                         "Authorization": "Token token={token}".format(token=api_token) }

    def get_schedules(self):
        """ Return a generator of schedule id, schedule_name """
        url = "{url}/schedules".format(url=self.url)
        r = requests.get(url, headers=self.headers)
        
        for schedule in r.json()['schedules']:
            yield schedule['id'], schedule['summary']

    def list_oncall(self,schedule_id):
        """ Return name and email of oncall for the given schedule_id """
        payload = {}
        since = datetime.utcnow().strftime('%Y-%m-%dT%H:%M')
        until = (datetime.utcnow()+timedelta(minutes=1)).strftime('%Y-%m-%dT%H:%M')

        url = "{url}/schedules/{schedule_id}/users".format(url=self.url, schedule_id=schedule_id)
        payload['since'] = "{since}Z".format(since=since)
        payload['until'] = "{until}Z".format(until=until)
        r = requests.get(url, headers=self.headers, params=payload)

        for user in r.json()['users']:
            name, email = user['name'], user['email']

        return name, email

    def get_schedule_id_from_name(self,schedule_name):
        """ Return schedule_id for the given schedule_name """
        schedule_id = None
        payload = {}
        url = "{url}/schedules".format(url=self.url)
        payload['query'] = schedule_name
        r = requests.get(url, headers=self.headers, params=payload)

        for schedule in r.json()['schedules']:
            schedule_id = schedule['id']

        return schedule_id


    def list_oncall_for_schedule(self, schedule_name):
        """ Return name, email of oncall for the given schedule_name """
        name, email = None, None
        schedule_id = self.get_schedule_id_from_name(schedule_name)
        if schedule_id:
            name, email = self.list_oncall(schedule_id)

        return name, email


    def list_all_oncalls(self):
        """ Return generator of (name, email, schedule_name) tuples for all schedules """
        for schedule_id, schedule_name in self.get_schedules():
            name, email = self.list_oncall(schedule_id)
            yield name, email, schedule_name



class PagerdutyPlugin(WillPlugin):

    @require_settings("PAGERDUTY_V2_TOKEN")
    @respond_to("^who[\s'is]*\son[\s]*call$")
    def whos_oncall(self, message):
        pager = Pagerduty(settings.PAGERDUTY_V2_TOKEN)
        response = ''
        for name, email, schedule in pager.list_all_oncalls():
            if name and email and schedule:
                response += "{name} ({email}) is oncall for {schedule}\n".format(name=name,
                                                           email=email,
                                                           schedule=schedule)

        self.reply(message, response)

    @require_settings("PAGERDUTY_V2_TOKEN")
    @respond_to("^who[\s'is]*\son[\s]*call\s[\Afor\z]*\s*(?P<schedule>.*$)")
    def whos_oncall_for(self, message, schedule):
        pager = Pagerduty(settings.PAGERDUTY_V2_TOKEN)
        name, email = pager.list_oncall_for_schedule(schedule)
        if name and email and schedule:
            response = "@{name} ({email}) is oncall for {schedule}\n".format(name=name.lower(),
                                                           email=email,
                                                           schedule=schedule)
        else:
            response = "Failed to fetch details for '{schedule}'".format(schedule=schedule)

        self.reply(message, response)
