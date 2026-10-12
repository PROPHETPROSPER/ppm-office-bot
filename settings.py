import os
from dotenv import load_dotenv
load_dotenv()

def setting(name, default=''):
    return os.getenv(name,default)

TOPICS = {
 'morning_prayer':'Morning Prayer',
 'evening_teaching':'Evening YouTube Teaching',
 'prayer_chain':'Prayer Chain',
 'schools':'Schools & Training',
 'gatherings':'In-person gatherings',
 'weekly_digest':'Weekly recap'
}
AUDIENCES = {
 'official':'TELEGRAM_OFFICIAL_CHANNEL_ID',
 'free':'TELEGRAM_FREE_GROUP_ID',
 'paid':'TELEGRAM_PAID_GROUP_ID'
}
PROMO_STAGES=(14,10,7,5,3,2,1,0)
# IMPORTANT: confidential plans never reside in public event marketing tables.
CONFIDENTIAL_TERMS=('dallas','relocation','relocating','jan 2027')
