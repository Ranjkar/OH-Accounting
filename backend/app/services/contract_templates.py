"""Built-in agreement template content (Phase 26) in Dutch and English.

LEGAL STATUS: this is a structured STARTING POINT, not legal advice and not
a reviewed contract. Every clause below must be reviewed and approved by a
Dutch legal professional before the template version is approved for
production use. Nothing here sets a price, a payment term or a notice
period -- those are nullable template defaults an administrator must fill
in; the code never invents commercial terms.

Clause bodies may reference these placeholders, substituted at render time
from the Company / Contract rows:
  {provider_name} {client_name} {client_kvk} {client_vat} {client_address}
  {client_representative} {start_date} {end_date} {term_months}
  {services} {fee} {payment_terms_days} {notice_period_days} {reference}
"""

from datetime import date

PROVIDER_NAME = "OnHolland Accounting"

SUPPORTED_LANGUAGES = ("nl", "en")

DEFAULT_SERVICES = [
    {"code": "bookkeeping", "nl": "Verwerken van de financiële administratie", "en": "Bookkeeping and processing of the financial administration"},
    {"code": "vat_returns", "nl": "Opstellen en indienen van btw-aangiften", "en": "Preparation and filing of VAT returns"},
    {"code": "annual_accounts", "nl": "Opstellen van de jaarrekening", "en": "Preparation of the annual accounts"},
    {"code": "income_tax", "nl": "Aangifte inkomstenbelasting / vennootschapsbelasting", "en": "Income tax / corporate income tax return"},
]

_NL_CLAUSES = [
    {"key": "parties", "heading": "1. Partijen", "body": "Deze overeenkomst wordt gesloten tussen {provider_name} (hierna: \"Opdrachtnemer\") en {client_name}, ingeschreven bij de Kamer van Koophandel onder nummer {client_kvk}, btw-identificatienummer {client_vat}, gevestigd te {client_address}, rechtsgeldig vertegenwoordigd door {client_representative} (hierna: \"Opdrachtgever\")."},
    {"key": "scope", "heading": "2. Omvang van de dienstverlening", "body": "Opdrachtnemer verricht voor Opdrachtgever de volgende diensten: {services}. Werkzaamheden buiten deze omschrijving worden uitsluitend uitgevoerd na schriftelijke opdracht en tegen de alsdan overeengekomen vergoeding."},
    {"key": "term", "heading": "3. Looptijd", "body": "De overeenkomst gaat in op {start_date} en wordt aangegaan voor een periode van {term_months} maanden, eindigend op {end_date}. Verlenging vindt uitsluitend plaats door het sluiten van een nieuwe, door beide partijen ondertekende overeenkomst. Het uitblijven van een reactie op een verlengingsvoorstel geldt niet als aanvaarding."},
    {"key": "fees", "heading": "4. Vergoeding en betaling", "body": "De vergoeding bedraagt {fee}. Facturen worden maandelijks verzonden en dienen binnen {payment_terms_days} dagen na factuurdatum te worden voldaan. Genoemde bedragen zijn exclusief btw, tenzij anders vermeld."},
    {"key": "responsibilities_client", "heading": "5. Verplichtingen van Opdrachtgever", "body": "Opdrachtgever draagt zorg voor tijdige, volledige en juiste aanlevering van alle voor de werkzaamheden benodigde gegevens en bescheiden en staat in voor de juistheid daarvan. Opdrachtgever blijft zelf verantwoordelijk voor de nakoming van zijn fiscale en administratieve verplichtingen."},
    {"key": "responsibilities_provider", "heading": "6. Verplichtingen van Opdrachtnemer", "body": "Opdrachtnemer voert de werkzaamheden naar beste vermogen en met de zorg van een goed opdrachtnemer uit, met inachtneming van de toepasselijke wet- en regelgeving en de voor het beroep geldende gedrags- en beroepsregels."},
    {"key": "confidentiality", "heading": "7. Geheimhouding", "body": "Partijen zijn verplicht tot geheimhouding van alle vertrouwelijke informatie die zij in het kader van deze overeenkomst van elkaar verkrijgen, behoudens voor zover een wettelijke plicht tot openbaarmaking bestaat."},
    {"key": "data_protection", "heading": "8. Gegevensbescherming", "body": "Voor zover Opdrachtnemer persoonsgegevens verwerkt ten behoeve van Opdrachtgever, handelen partijen in overeenstemming met de Algemene verordening gegevensbescherming (AVG). Waar vereist sluiten partijen een afzonderlijke verwerkersovereenkomst. Opdrachtnemer bewaart de administratie gedurende de wettelijke bewaartermijn."},
    {"key": "liability", "heading": "9. Aansprakelijkheid", "body": "[Door een jurist in te vullen: beperking van aansprakelijkheid, uitsluitingen en verzekerde som.]"},
    {"key": "termination", "heading": "10. Opzegging en beëindiging", "body": "Ieder der partijen kan de overeenkomst tegen het einde van de looptijd schriftelijk opzeggen met inachtneming van een opzegtermijn van {notice_period_days} dagen. Tussentijdse beëindiging is mogelijk indien de wederpartij toerekenbaar tekortkomt en na schriftelijke ingebrekestelling niet binnen een redelijke termijn alsnog nakomt, alsmede bij faillissement of surseance van betaling."},
    {"key": "renewal", "heading": "11. Verlenging", "body": "Uiterlijk {notice_period_days} dagen voor het einde van de looptijd zendt Opdrachtnemer een voorstel voor een nieuwe overeenkomst van {term_months} maanden toe. Een nieuwe overeenkomst komt uitsluitend tot stand door elektronische ondertekening door Opdrachtgever."},
    {"key": "electronic_signature", "heading": "12. Elektronische ondertekening", "body": "Partijen stemmen ermee in dat deze overeenkomst elektronisch wordt ondertekend door middel van een gewone elektronische handtekening in de zin van artikel 3, onder 10, van Verordening (EU) nr. 910/2014 (eIDAS). De door Opdrachtgever ingevoerde naam, het e-mailadres van de ondertekenaar, het tijdstip van ondertekening en de SHA-256-hash van het ondertekende document worden als bewijs vastgelegd. Dit betreft geen gekwalificeerde elektronische handtekening."},
    {"key": "law", "heading": "13. Toepasselijk recht", "body": "Op deze overeenkomst is Nederlands recht van toepassing. Geschillen worden voorgelegd aan de bevoegde rechter in het arrondissement waar Opdrachtnemer is gevestigd."},
]

_EN_CLAUSES = [
    {"key": "parties", "heading": "1. Parties", "body": "This agreement is entered into between {provider_name} (the \"Provider\") and {client_name}, registered with the Dutch Chamber of Commerce under number {client_kvk}, VAT identification number {client_vat}, having its registered office at {client_address}, duly represented by {client_representative} (the \"Client\")."},
    {"key": "scope", "heading": "2. Scope of services", "body": "The Provider shall perform the following services for the Client: {services}. Work outside this description is performed only on written instruction and at the fee then agreed."},
    {"key": "term", "heading": "3. Term", "body": "This agreement commences on {start_date} and is entered into for a period of {term_months} months, ending on {end_date}. Renewal takes place solely by concluding a new agreement signed by both parties. Silence in response to a renewal proposal does not constitute acceptance."},
    {"key": "fees", "heading": "4. Fees and payment", "body": "The fee amounts to {fee}. Invoices are issued monthly and are payable within {payment_terms_days} days of the invoice date. Amounts are exclusive of VAT unless stated otherwise."},
    {"key": "responsibilities_client", "heading": "5. Client responsibilities", "body": "The Client shall supply all information and documents required for the services in a timely, complete and accurate manner and warrants their accuracy. The Client remains responsible for compliance with its own tax and administrative obligations."},
    {"key": "responsibilities_provider", "heading": "6. Provider responsibilities", "body": "The Provider shall perform the services to the best of its ability and with the care of a competent professional, in accordance with applicable law and the professional rules governing the profession."},
    {"key": "confidentiality", "heading": "7. Confidentiality", "body": "Each party shall keep confidential all confidential information obtained from the other party in connection with this agreement, except where disclosure is required by law."},
    {"key": "data_protection", "heading": "8. Data protection", "body": "Insofar as the Provider processes personal data on behalf of the Client, the parties act in accordance with the General Data Protection Regulation (GDPR). Where required, the parties conclude a separate data processing agreement. The Provider retains the administration for the statutory retention period."},
    {"key": "liability", "heading": "9. Liability", "body": "[To be completed by legal counsel: limitation of liability, exclusions and insured amount.]"},
    {"key": "termination", "heading": "10. Notice and termination", "body": "Either party may terminate this agreement in writing with effect from the end of the term, observing a notice period of {notice_period_days} days. Early termination is possible if the other party is in attributable breach and fails to remedy within a reasonable period after written notice of default, and in the event of bankruptcy or suspension of payments."},
    {"key": "renewal", "heading": "11. Renewal", "body": "No later than {notice_period_days} days before the end of the term, the Provider shall send a proposal for a new {term_months}-month agreement. A new agreement is concluded only upon electronic signature by the Client."},
    {"key": "electronic_signature", "heading": "12. Electronic signature", "body": "The parties agree that this agreement is signed electronically by means of a simple electronic signature within the meaning of Article 3(10) of Regulation (EU) No 910/2014 (eIDAS). The name entered by the Client, the signer's email address, the time of signing and the SHA-256 hash of the signed document are recorded as evidence. This is not a qualified electronic signature."},
    {"key": "law", "heading": "13. Governing law", "body": "This agreement is governed by Dutch law. Disputes shall be submitted to the competent court in the district where the Provider has its registered office."},
]

DEFAULT_CONTENT = {
    "nl": {"title": "Overeenkomst administratieve dienstverlening", "clauses": _NL_CLAUSES},
    "en": {"title": "Accounting Services Agreement", "clauses": _EN_CLAUSES},
}

LABELS = {
    "nl": {
        "reference": "Referentie", "parties": "Partijen", "provider": "Opdrachtnemer", "client": "Opdrachtgever",
        "kvk": "KVK-nummer", "vat": "Btw-id", "address": "Adres", "representative": "Vertegenwoordigd door",
        "term": "Looptijd", "term_value": "{months} maanden, van {start} tot en met {end}", "services": "Diensten",
        "fee": "Vergoeding", "fee_monthly": "{amount} per maand (excl. btw)", "fee_unset": "nog niet vastgesteld",
        "payment_terms": "Betalingstermijn", "days": "{n} dagen", "notice_period": "Opzegtermijn", "not_set": "n.n.b.",
        "signature_block": "Ondertekening", "unsigned_note": "Nog niet ondertekend.", "signed_by": "Elektronisch ondertekend door",
        "signed_at": "Ondertekend op (UTC)", "signer_email": "E-mailadres ondertekenaar", "method": "Ondertekeningsmethode",
        "method_value": "Gewone elektronische handtekening (eIDAS art. 3(10)): e-maillink + ingevoerde naam + uitdrukkelijke instemming. Geen gekwalificeerde elektronische handtekening.",
        "consent": "Instemmingstekst", "document_hash": "SHA-256 van het ondertekende document", "evidence_title": "Bewijs van elektronische ondertekening",
        "legal_note": "Conceptsjabloon -- te beoordelen door een Nederlandse jurist voor productiegebruik.", "ip": "IP-adres",
        "consent_text": "Ik, {name}, verklaar dat ik deze overeenkomst volledig heb gelezen, dat ik bevoegd ben {client_name} te vertegenwoordigen, en dat ik ermee instem deze overeenkomst elektronisch te ondertekenen met een gewone elektronische handtekening. Ik begrijp dat mijn ingevoerde naam, e-mailadres, het tijdstip en de documenthash als bewijs worden vastgelegd.",
        "none": "geen",
    },
    "en": {
        "reference": "Reference", "parties": "Parties", "provider": "Provider", "client": "Client",
        "kvk": "KVK number", "vat": "VAT id", "address": "Address", "representative": "Represented by",
        "term": "Term", "term_value": "{months} months, from {start} to {end} inclusive", "services": "Services",
        "fee": "Fee", "fee_monthly": "{amount} per month (excl. VAT)", "fee_unset": "not yet set",
        "payment_terms": "Payment terms", "days": "{n} days", "notice_period": "Notice period", "not_set": "t.b.d.",
        "signature_block": "Signature", "unsigned_note": "Not yet signed.", "signed_by": "Electronically signed by",
        "signed_at": "Signed at (UTC)", "signer_email": "Signer email", "method": "Signing method",
        "method_value": "Simple electronic signature (eIDAS art. 3(10)): emailed link + typed name + explicit consent. Not a qualified electronic signature.",
        "consent": "Consent text", "document_hash": "SHA-256 of the signed document", "evidence_title": "Electronic signature evidence",
        "legal_note": "Draft template -- to be reviewed by a Dutch legal professional before production use.", "ip": "IP address",
        "consent_text": "I, {name}, confirm that I have read this agreement in full, that I am authorised to represent {client_name}, and that I agree to sign this agreement electronically using a simple electronic signature. I understand that my typed name, email address, the time of signing and the document hash are recorded as evidence.",
        "none": "none",
    },
}


def normalize_language(code: str | None) -> str:
    return code if code in SUPPORTED_LANGUAGES else "nl"


def label(language: str, key: str, **params: object) -> str:
    return LABELS[normalize_language(language)][key].format(**params)


def format_date(value: date, language: str) -> str:
    return value.strftime("%d-%m-%Y") if normalize_language(language) == "nl" else value.strftime("%d %B %Y")


def format_money(amount, language: str) -> str:
    text = f"{amount:,.2f}"
    if normalize_language(language) == "nl":
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"EUR {text}"
