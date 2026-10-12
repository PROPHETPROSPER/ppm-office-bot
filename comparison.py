"""Illustrative comparison: indicators are not proof that any engagement is fake."""
from decimal import Decimal

def compare_scenarios(scenarios):
    ret=[]
    for s in scenarios:
        impressions=max(0,int(s.get('impressions',0)))
        clicks=max(0,int(s.get('profile_or_link_clicks',0)))
        joined=max(0,int(s.get('verified_opt_ins',0)))
        attended=max(0,int(s.get('verified_attendance',0)))
        recurring=max(0,int(s.get('returning_attendees',0)))
        if recurring>attended:raise ValueError('Returning attendees cannot exceed verified attendance')
        ret.append({
         'label':s.get('label','Scenario'),
         'impressions':impressions,
         'click_through_pct':round(100*clicks/impressions,2) if impressions else None,
         'opt_in_pct_of_clicks':round(100*joined/clicks,2) if clicks else None,
         'attendance_pct_of_opt_ins':round(100*attended/joined,2) if joined else None,
         'returning_pct_of_attendees':round(100*recurring/attended,2) if attended else None,
         'verified_opt_ins':joined,'verified_attendance':attended,
         'note':'Scenario metrics only. Low conversion is not proof of fake engagement; inspect acquisition and audience fit.'
        })
    return {'comparisons':ret,'notice':'No engagement or order creation, and no claims about specific real accounts.'}
