from calendar import monthrange
import pandas as pd
from datetime import datetime

def safe_due_date(start_date, i, due_day):
    temp = datetime.date(start_date) + pd.DateOffset(months=i)
    last_day = monthrange(temp.year, temp.month)[1]
    return temp.replace(day=min(due_day, last_day))