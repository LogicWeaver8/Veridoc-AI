"""One-off generator for the demo PDF (requires PyMuPDF)."""

from __future__ import annotations

from pathlib import Path

import pymupdf

OUT = Path(__file__).parent / "demo_documents" / "Office_Access_and_Facilities_2026.pdf"

PARAGRAPHS = [
    ("h1", "Office Access and Facilities Policy"),
    ("p", "Document owner: Workplace Services | Version: 2026.1 | Effective date: 1 January 2026"),
    ("h2", "1. Purpose"),
    ("p", "This policy explains how employees, contractors and visitors access VeriDox offices, "
          "book shared spaces and behave in communal areas. It applies to the Bengaluru and Pune offices."),
    ("h2", "2. Access badges"),
    ("p", "Every employee receives a photo access badge on the first day. Badges are personal and may "
          "not be shared or loaned. Lost badges must be reported to Workplace Services the same day; a "
          "replacement costs INR 500 and is deducted from payroll unless the loss is reported as theft "
          "with a police complaint."),
    ("p", "Badges are deactivated on the last working day. Contractors receive time-limited badges that "
          "expire automatically at the end of their engagement."),
    ("h2", "3. Office hours"),
    ("p", "Offices are open from 07:00 to 22:00 on business days. Access outside these hours requires "
          "manager approval recorded in the facilities portal at least 4 hours in advance. Weekend access "
          "requires approval from a director."),
    ("p", "The Bengaluru office is closed on public holidays listed on the intranet. Employees who need "
          "to work on a public holiday may use the Pune office if it is open, subject to approval."),
    ("h2", "4. Visitors"),
    ("p", "All visitors must be pre-registered by the hosting employee at least 2 hours before arrival. "
          "Visitors sign in at reception, show a government-issued photo ID and wear a visitor badge at "
          "all times. Hosts must escort visitors in secure areas and remain with them for the duration of "
          "the visit."),
    ("p", "Customer visits that involve access to Restricted data require approval from Information "
          "Security and must take place in a closed meeting room."),
    ("h2", "5. Meeting rooms"),
    ("p", "Meeting rooms may be booked up to 14 days in advance. Bookings are released automatically "
          "after 10 minutes if the room is not occupied. Rooms with video-conferencing equipment are "
          "reserved for hybrid meetings and may not be booked for individual focus work."),
    ("p", "Employees must leave rooms tidy and erase whiteboards that contain confidential information."),
    ("h2", "6. Parking"),
    ("p", "Parking is allocated by lottery every quarter. Employees with a disability certificate receive "
          "a reserved bay on request. Two-wheeler parking is available on a first-come basis and does not "
          "require registration."),
    ("h2", "7. Cafeteria and communal areas"),
    ("p", "The cafeteria serves breakfast and lunch on business days. Food may not be taken into meeting "
          "rooms with carpets or into the hardware lab. Employees are expected to clean up after "
          "themselves and separate waste into the labelled bins."),
    ("h2", "8. Emergency procedures"),
    ("p", "Fire wardens are identified on each floor. On hearing the evacuation alarm, employees must "
          "leave by the nearest stairwell, not the lifts, and assemble at the designated point in the "
          "parking area. Floor wardens take a headcount and report missing persons to the safety officer."),
    ("p", "First-aid kits are located at reception and in each pantry. Defibrillators are available in the "
          "Bengaluru lobby and the Pune third-floor reception."),
    ("h2", "9. Reporting facilities issues"),
    ("p", "Raise facilities requests through the workplace portal. Urgent issues such as water leaks, "
          "electrical faults or broken access doors should be reported to the facilities hotline "
          "immediately. Safety hazards must never be left unattended."),
    ("h2", "10. Review"),
    ("p", "Workplace Services reviews this policy every year with input from Information Security and the "
          "safety committee. The next review is due in December 2026."),
]

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; color: #1d2a24; }
h1 { font-size: 20pt; margin: 0 0 14pt 0; }
h2 { font-size: 13pt; margin: 16pt 0 6pt 0; }
p { margin: 0 0 8pt 0; }
"""


def main() -> None:
    body = "".join(f"<{tag}>{text}</{tag}>" for tag, text in PARAGRAPHS)
    html = f"<html><head><style>{CSS}</style></head><body>{body}</body></html>"
    story = pymupdf.Story(html=html)
    writer = pymupdf.DocumentWriter(str(OUT))
    mediabox = pymupdf.paper_rect("a4")
    content_rect = mediabox + (56, 56, -56, -56)
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()
    document = pymupdf.open(OUT)
    print(f"Wrote {OUT} ({document.page_count} pages)")
    document.close()


if __name__ == "__main__":
    main()
