import calendar

def get_month_name(month: int) -> str:
    """Returns the full English name of the month (1-12)."""
    if 1 <= month <= 12:
        return calendar.month_name[month]
    return f"Month {month}"

def mask_account_number(account_number: str) -> str:
    """Masks a bank account number showing only the last 4 digits in official format."""
    if not account_number:
        return "N/A"
    clean = str(account_number).strip()
    if len(clean) <= 4:
        return clean
    return "X" * (len(clean) - 4) + clean[-4:]

def number_to_words(num: float, currency_symbol: str = "$") -> str:
    """Converts a monetary number into standard English words with support for international and Indian numbering systems."""
    try:
        is_rupee = currency_symbol in ["₹", "INR", "Rs", "Rs.", "rupees", "Rupees"]
        currency_name = "Rupees" if is_rupee else "Dollars"
        
        units = [
            "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
            "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"
        ]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

        def helper_western(n: int) -> str:
            if n == 0:
                return ""
            elif n < 20:
                return units[n] + " "
            elif n < 100:
                return tens[n // 10] + (" " + units[n % 10] if n % 10 != 0 else "") + " "
            elif n < 1000:
                return units[n // 100] + " Hundred " + helper_western(n % 100)
            elif n < 1000000:
                return helper_western(n // 1000) + "Thousand " + helper_western(n % 1000)
            elif n < 1000000000:
                return helper_western(n // 1000000) + "Million " + helper_western(n % 1000000)
            else:
                return helper_western(n // 1000000000) + "Billion " + helper_western(n % 1000000000)

        def helper_indian(n: int) -> str:
            if n == 0:
                return ""
            elif n < 20:
                return units[n] + " "
            elif n < 100:
                return tens[n // 10] + (" " + units[n % 10] if n % 10 != 0 else "") + " "
            elif n < 1000:
                return units[n // 100] + " Hundred " + helper_indian(n % 100)
            elif n < 100000:
                return helper_indian(n // 1000) + "Thousand " + helper_indian(n % 1000)
            elif n < 10000000:
                return helper_indian(n // 100000) + "Lakh " + helper_indian(n % 100000)
            else:
                return helper_indian(n // 10000000) + "Crore " + helper_indian(n % 10000000)

        int_part = int(abs(num))
        cents = int(round((abs(num) - int_part) * 100))

        if int_part == 0:
            words = "Zero "
        else:
            words = helper_indian(int_part) if is_rupee else helper_western(int_part)

        words = words.strip() + f" {currency_name}"

        if cents > 0:
            cents_name = "Paise" if is_rupee else "Cents"
            words += f" and {cents}/100 {cents_name}"

        words += " Only"
        if num < 0:
            words = "Minus " + words
        return words
    except Exception:
        return f"{num:.2f} Only"
