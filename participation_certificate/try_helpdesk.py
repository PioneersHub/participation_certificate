# import json
#
# from pytanis.helpdesk import HelpDeskClient
#
#
# class MyHelpDeskClient(HelpDeskClient):
#     def get_tickets(self, page=1):
#         return self.get(endpoint="tickets", params={"page": page})
#
#
# hdc = MyHelpDeskClient()
# hdc.set_throttling(1,1)
# all_res = []
# for i in range(1, 100):
#     res = hdc.get_tickets(i)
#     if not sum([x["subject"] == "Certificate of Attendance: PyCon.DE & PyData Berlin 2024" for x in res]):
#         break
#
#     all_res.extend(res)
#
# json.dump(all_res, open("sent.json", "w"), indent=4)
# as_set = {x["requester"]["email"].lower() for x in all_res}
# a = 44

import hashlib
from pathlib import Path

from pydantic import UUID4

invalidate = list(
    zip(
        """Jochen Stein
Jonas Kapitzke


Renee Chebbo
Joachim Schmidt
Dânia Meira
Erik Price
Karim Meiborg
Zoran Štefanić
René Rivero Arrieta
Anja Pilz
Maximilian Seyrich
Jan Wagner
Jens Nie
Alejandro Agustin
Maryam Pourranjbar
Martin Schneider
Anne Ernst
Tobias Sterbak
Richard Baffour-Awuah
Yeonjoo Yoo
Klaus Wiebe

Juan Luis Cano Rodríguez
Richard Schulz
Hafiz Faheim Rehman
Alexander Vosseler
Wei Ding

Domenic Gilardoni
Nikita Kudriavtsev
Ilnur Ismagilov
Ekaterina Shvorneva
Stanislav Sopov
Kirill Puchkov
Alexander Fechler
Irati Rodriguez
Christian Moreau
Benjamin Thomas Schwertfeger
Alessia Cavallo
Artemii Dubovoi
Gabrielle Simard-Moore
Eshan Mushtaq
Jose Ciurana Cruz
Soumen Ganguly
Maximilian Siska
Bruno Moesch
Tido Felix Marschall
Viktoria Könitz
Patrick Busenius
Adrian Theopold
Benjamin Wolff
Paul Romieu
Pierre Ouchene
Océane Haddad
Domingo Gomes
Ken McGrady
Johannes Rieke
Benjamin Räthlein
Joshua Carroll
Gonçalo Faria
Marko Thiele
Thuy-Vi Vo-Blaschke

Patrick Hoebeke

Patrick Hoefler
Lilo Wagner
Rohit Bhisikar
Markus Mauder
Martin Lechner
Leonard Kern
Julie Fang



Bita Najdahmadi
Bita Najdahmadi
Bita Najdahmadi
Maximilian Robert
Christian Lengert""".split("\n"),
        """SUHJ-1
LMYC-1
STPS-1
QJGH-1
DYBB-1
MCS2-1
BL7S-1
UEUI-1
QY97-1
ZTLX-1
DZFZ-1
FFCS-1
7YPS-1
ERBH-1
4WLT-1
LVFF-1
PCLS-1
5JRK-2
5JRK-3
PYIS-1
N1DY-1
QXTC-1
MZ87-1
WKCB-1
NNFW-1
Y7NY-2
KDEE-1
AYCV-1
UY94-1
XKET-1
1M3J-2
DDDP-1
DDDP-2
DDDP-3
DDDP-4
DDDP-5
KAP7-1
H3MV-1
UVA6-1
9NPR-1
QHR6-1
CJFJ-1
INCT-1
JUCD-1
YDDA-5
2E8B-1
6DMR-1
JHHA-1
LJ3Y-1
J7XV-1
RYCD-1
8F8D-1
ZSUC-1
4DZB-1
4DZB-2
CDTP-1
CDTP-2
9PJ7-1
2G4R-1
MKKJ-1
DDBL-1
YXC4-1
C21K-3
6RME-1
KEQJ-2
E2GD-1
CYRZ-1
E8JA-2
GIEW-3
YUTR-1
ZGZ7-1
2CQC-1
FMZ8-1
QMHD-1
E4ET-1
E4ET-2
E4ET-3
FW5Y-1
FW5Y-2
FW5Y-3
UXEV-1
4NHX-1""".split("\n"),
        strict=False,
    )
)

for name, ticket in invalidate:
    hash_this = "".join([x.upper() for x in name if x.isalnum()]) + ticket.strip()
    hsh = hashlib.sha512()
    hsh.update(hash_this.encode("utf-8"))
    # stable uuid for webservice, this uuid will always be the same for the same attendee
    # allows reruns without cleanup
    uuid = str(UUID4(hsh.hexdigest()[:32]))
    p = (
        Path("/Users/hendorf/code/pycommunity/pyconde_www/website/content/attendee-certificate")
        / uuid
        / "contents.lr"
    )
    if p.exists():
        print(uuid, "exists")
        p.open("w").write("""_model: validate_certificate
---
title: INVALID CERTIFICATE
---
full_name: UNKNOWN
---
conference: INVALID CERTIFICATE
---
hash: UNKNOWN
---
_discoverable: no""")
    c = (
        Path(
            "/Users/hendorf/code/pioneershub/participation_certificate/_certificates/2024-pycon_de_upload"
        )
        / f"{uuid}.pdf"
    )
    if c.exists():
        print(uuid, "PDF exists")
        c.rename(c.with_suffix(".invalid.pdf"))
