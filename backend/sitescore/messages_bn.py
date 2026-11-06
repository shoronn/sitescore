"""Bangla for the messages the API shows visitors (errors and failed scans).

The API speaks English by default. A visitor using the Bangla site sends
Accept-Language: bn, and these replace the English messages.
"""
from __future__ import annotations

import re

MESSAGES_BN = {
    "Request is too large.": "অনুরোধটি অনেক বড়।",
    "Please check this field.": "এই ঘরটি আবার দেখুন।",
    "Please enter your email to continue.": "চালিয়ে যেতে আপনার ইমেইল দিন।",
    "Too many tries from your network. Please try again in an hour.":
        "আপনার নেটওয়ার্ক থেকে অনেকবার চেষ্টা করা হয়েছে। এক ঘণ্টা পরে আবার চেষ্টা করুন।",
    "Please complete the security check and try again.": "নিরাপত্তা যাচাইটি সম্পূর্ণ করে আবার চেষ্টা করুন।",
    "You have reached today's free scan limit. Please try again tomorrow.":
        "আজকের ফ্রি স্ক্যানের সীমা শেষ। আগামীকাল আবার চেষ্টা করুন।",
    "We could not find that scan.": "এই স্ক্যানটি আমরা খুঁজে পাইনি।",
    "This results link has expired. Run a new scan to see fresh results.":
        "এই রেজাল্ট লিংকের মেয়াদ শেষ। নতুন রেজাল্ট দেখতে আবার স্ক্যান করুন।",
    "Too many downloads. Please try again later.": "অনেকবার ডাউনলোড হয়েছে। একটু পরে আবার চেষ্টা করুন।",
    "The report is ready once the scan has finished.": "স্ক্যান শেষ হলেই রিপোর্ট তৈরি হবে।",
    "The scan took too long and was stopped. Please try again.":
        "স্ক্যানে অনেক বেশি সময় লাগায় এটি থামানো হয়েছে। আবার চেষ্টা করুন।",
    "Please enter a valid email address you can receive mail at.": "এমন একটি সঠিক ইমেইল ঠিকানা দিন যেখানে আপনি মেইল পান।",
    "Please use your regular email address, not a temporary one.": "অস্থায়ী নয়, আপনার নিয়মিত ইমেইল ঠিকানা ব্যবহার করুন।",
    "Please enter a valid phone number, or leave it empty.": "সঠিক একটি ফোন নম্বর দিন, অথবা ঘরটি খালি রাখুন।",
    "Please enter a website address.": "একটি ওয়েবসাইটের ঠিকানা দিন।",
    "That does not look like a website address.": "এটি ওয়েবসাইটের ঠিকানার মতো দেখাচ্ছে না।",
    "That does not look like a public website address.": "এটি কোনো পাবলিক ওয়েবসাইটের ঠিকানার মতো দেখাচ্ছে না।",
    "Only http and https websites can be scanned.": "শুধু http আর https ওয়েবসাইট স্ক্যান করা যায়।",
    "Only standard web ports (80 and 443) can be scanned.": "শুধু সাধারণ ওয়েব পোর্ট (৮০ আর ৪৪৩) স্ক্যান করা যায়।",
    "Please enter a domain name, not an IP address.": "IP ঠিকানা নয়, একটি ডোমেইন নাম দিন।",
    "The owner of this website has asked us not to scan it.": "এই ওয়েবসাইটের মালিক আমাদের এটি স্ক্যান না করতে বলেছেন।",
    "Something went wrong on our side. Please try again.": "আমাদের দিকে একটি সমস্যা হয়েছে। আবার চেষ্টা করুন।",
}

_PATTERNS = [
    (re.compile(r"^(.+) does not resolve to any address\. Check the spelling\.$"),
     "{0}-এর কোনো ঠিকানা পাওয়া যায়নি। বানানটি আবার দেখুন।"),
    (re.compile(r"^(.+) points to a private or reserved address and cannot be scanned\.$"),
     "{0} একটি প্রাইভেট বা সংরক্ষিত ঠিকানা দেখায়, তাই স্ক্যান করা যায় না।"),
]


def wants_bangla(accept_language: str | None) -> bool:
    """True when the visitor's first language choice is Bangla."""
    first = (accept_language or "").split(",")[0].strip().lower()
    return first.startswith("bn")


def to_bangla(message: str | None) -> str | None:
    if not message:
        return message
    if message in MESSAGES_BN:
        return MESSAGES_BN[message]
    for pattern, template in _PATTERNS:
        m = pattern.match(message)
        if m:
            return template.format(*m.groups())
    return message
