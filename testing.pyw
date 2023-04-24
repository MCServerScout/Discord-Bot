import datetime


def timeAgo(self, date: datetime.datetime) -> str:
    """Returns a string of how long ago a date was

    Args:
        date (datetime.datetime): The date to compare

    Returns:
        str: The string of how long ago the date was (now if less than 30 seconds ago)
    """

    diff = datetime.datetime.utcnow() - date

    if datetime.timedelta(seconds=30) > diff:
        return "now"

    months = diff.days // 30
    days = diff.days % 30
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    seconds = (diff.seconds % 3600) % 60
    
    out = ""
    
    if months:
        out += f"{months} month{'s' if months > 1 else ''}, "
    if days:
        out += f"{days} day{'s' if days > 1 else ''}, "
    if hours:
        out += f"{hours} hour{'s' if hours > 1 else ''}, "
    if minutes:
        out += f"{minutes} minute{'s' if minutes > 1 else ''}, "
    if seconds:
        out += f"{seconds} second{'s' if seconds > 1 else ''}"
    
    return out


time = datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=1, minutes=1, seconds=1)

print(timeAgo(None, time))
