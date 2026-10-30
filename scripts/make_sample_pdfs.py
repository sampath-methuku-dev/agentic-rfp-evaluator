"""Generate four fictional supplier proposals (plus one unreadable PDF for error testing).

    python scripts/make_sample_pdfs.py
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sample_rfps"
ERR = ROOT / "data" / "error_cases"

REQUEST = ("RFP-2026-017: Supplier Contract Management Platform. The buyer needs a cloud "
           "platform to store contracts, track obligations and renewals, integrate with its "
           "ERP and identity provider, and go live within 6 months for about 800 users.")

SUPPLIERS = {
    "Apex_Systems": {
        "name": "Apex Systems",
        "summary": ["Apex Systems proposes a modular, API-first contract platform on a multi-region cloud architecture. We have read RFP-2026-017 and understand the need for obligation tracking, renewal alerts, ERP integration and single sign-on for 800 users.",
                    "Our design favours scalability and security over speed of delivery, which is reflected in a premium price and a 7-month schedule."],
        "solution": ["Architecture: microservices on Kubernetes with an event bus, a document store with full-text search, and a rules engine for obligation alerts. Horizontal autoscaling is tested to 5,000 concurrent users, six times the stated need.",
                     "Integrations: certified connectors for SAP and Oracle ERP via REST and message queues, SAML 2.0 / OIDC single sign-on, and a documented public API with 140 endpoints. Data migration uses an automated import tool with validation reports.",
                     "Approach: discovery, build in four increments, user acceptance testing, phased roll-out by department."],
        "timeline": ["Total duration 7 months. Milestones: M1 discovery and design sign-off (month 1), M2 core platform (month 3), M3 ERP integration complete (month 5), M4 UAT (month 6), M5 go-live (month 7).",
                     "Team: 1 programme manager, 1 solution architect, 5 engineers, 2 QA engineers, 1 security engineer, 1 change manager. Named leads are provided in Appendix A."],
        "price": [["Item", "Cost (USD)"], ["Licences, 800 users, 3 years", "612,000"], ["Implementation services", "340,000"], ["Data migration", "55,000"], ["Training", "30,000"], ["Total (3 years)", "1,037,000"]],
        "assumptions": "Prices exclude taxes and travel. Up to 20 custom reports included; extra reports at 1,800 USD each. Annual licence uplift capped at 4%.",
        "security": ["Certifications: ISO 27001 and SOC 2 Type II, audited annually; reports available under NDA. GDPR compliant with EU data residency option.",
                     "Controls: encryption at rest (AES-256) and in transit (TLS 1.3), role-based access with quarterly access reviews, immutable audit logs retained 7 years, annual third-party penetration tests, and a 4-hour incident notification commitment.",
                     "Risks: ERP interface complexity and data quality. Mitigation: early integration spike and a migration dry run."],
        "support": ["24x7 support with a 30-minute response for severity 1 and a named customer success manager. 99.95% uptime SLA with service credits.",
                    "Experience: 14 comparable contract platforms delivered in the last 5 years. References: a European bank (2,100 users) and a logistics group (900 users); contacts available on request."],
    },
    "BrightPath_Tech": {
        "name": "BrightPath Tech",
        "summary": ["BrightPath Tech offers the lowest-cost route to a working contract repository. We can have a first version live in 3 months using our standard product with light configuration.",
                    "We are a young company focused on speed and price."],
        "solution": ["Architecture: single-tenant application on one cloud region with nightly backups. Standard connectors cover CSV import and a basic REST API; ERP integration is done by file exchange.",
                     "Single sign-on supports SAML. Advanced obligation tracking is planned for a later release.",
                     "Approach: configure the standard product, load contracts, train users and go live."],
        "timeline": ["Total duration 3 months. Milestones: configuration (month 1), data load and training (month 2), go-live (month 3).",
                     "Team: 1 project manager and 3 consultants. Backup staffing is not defined."],
        "price": [["Item", "Cost (USD)"], ["Licences, 800 users, 3 years", "288,000"], ["Implementation services", "90,000"], ["Data migration", "15,000"], ["Training", "7,000"], ["Total (3 years)", "400,000"]],
        "assumptions": "Fixed price. Customer provides data in CSV format. Extra integrations quoted separately.",
        "security": ["We follow industry best practices and use encrypted storage. A SOC 2 audit is being planned. We do not currently hold ISO 27001.",
                     "Detailed privacy and data residency documentation is available on request."],
        "support": ["Support is available on business days, 9am to 6pm, by email with a next-business-day response. No uptime SLA is offered.",
                    "Experience: 3 customer deployments, all with fewer than 200 users. One reference is available."],
    },
    "NexaWorks": {
        "name": "NexaWorks",
        "summary": ["NexaWorks proposes a proven contract management product delivered through a structured, low-risk programme. We understand the need to go live within 6 months with ERP and identity integration for 800 users.",
                    "Our strengths are a detailed, risk-managed implementation plan and a strong support model, at a mid-range price."],
        "solution": ["Architecture: multi-tenant cloud platform with two regions and automatic failover. Standard connectors for major ERP systems and SAML/OIDC single sign-on; a REST API with 60 endpoints.",
                     "Approach: a 5-phase delivery method (mobilise, design, build, test, deploy) with a joint steering committee and a fortnightly demo of working software."],
        "timeline": ["Total duration 5.5 months. Milestones: M1 mobilisation and plan baseline (week 3), M2 design sign-off (week 8), M3 build complete (week 16), M4 integration and UAT (week 20), M5 go-live (week 23), M6 hypercare ends (week 27).",
                     "Team: programme manager, delivery lead, 4 engineers, 2 testers, 1 training specialist, with named backups for each role. A risk register is maintained weekly; the top 10 risks and mitigations are in Appendix B."],
        "price": [["Item", "Cost (USD)"], ["Licences, 800 users, 3 years", "468,000"], ["Implementation services", "210,000"], ["Data migration", "30,000"], ["Training and hypercare", "27,000"], ["Total (3 years)", "735,000"]],
        "assumptions": "Prices exclude taxes. Fixed price for the defined scope; change requests priced at the rate card attached. Licence uplift capped at 3% a year.",
        "security": ["Certifications: ISO 27001 certified; SOC 2 Type II report expected next quarter. GDPR compliant.",
                     "Controls: encryption at rest and in transit, role-based access, audit logging, and annual penetration testing."],
        "support": ["24x5 support with a 1-hour response for severity 1, a dedicated service manager, monthly service reviews and a 99.9% uptime SLA. A customer training academy and a user community are included.",
                    "Experience: 9 deployments of 500 to 1,500 users. Two references are provided with contact details."],
    },
    "Orbit_Digital": {
        "name": "Orbit Digital",
        "summary": ["Orbit Digital has delivered contract and document platforms for large organisations for over 15 years. We are confident we can meet the objectives of RFP-2026-017.",
                    "Our proposal highlights our experience and references."],
        "solution": ["Architecture: a mature platform with a flexible integration layer. We will integrate with the customer's ERP and other systems as needed using our standard approach.",
                     "Details of the interfaces will be agreed during the design phase. Single sign-on will be supported."],
        "timeline": ["Estimated duration 6 months, subject to design outcomes. Main phases: design, build, test, go-live. Detailed milestones will be confirmed after kick-off.",
                     "Team: a project team of suitable size will be assigned."],
        "price": [["Item", "Cost (USD)"], ["Licences, 800 users, 3 years", "540,000"], ["Implementation services", "250,000"], ["Data migration and training", "45,000"], ["Total (3 years)", "835,000"]],
        "assumptions": "Prices are indicative and exclude taxes. Integration effort is estimated and may change after design.",
        "security": ["ISO 27001 and SOC 2 Type II certified. Data is encrypted and access is role-based. Audit logs are kept for 3 years.",
                     "Penetration tests are performed every two years."],
        "support": ["24x7 support with a 1-hour response for severity 1 and a 99.9% uptime SLA.",
                    "Experience: over 60 deployments across 12 countries, including 20 with more than 1,000 users. Five detailed references are provided with contact details, including a government agency and a pharmaceutical company."],
    },
    "Summit_Cloud": {
        "name": "Summit Cloud",
        "summary": ["Summit Cloud proposes a highly secure, compliance-first contract platform for regulated industries. We have reviewed RFP-2026-017 and understand the need for obligation tracking, ERP integration and single sign-on for 800 users.",
                    "Our focus is security and auditability. This results in the highest price of the proposals we expect you to receive and a longer schedule."],
        "solution": ["Architecture: single-tenant deployment in a dedicated private cloud with customer-managed encryption keys. Integration is through a certified API gateway; ERP connectors for SAP are included, other ERPs are built to order.",
                     "Approach: a gated delivery model with a formal security review at the end of every phase, followed by a staged production roll-out."],
        "timeline": ["Total duration 9 months. Milestones: M1 security architecture approval (month 2), M2 platform build (month 5), M3 SAP integration (month 7), M4 penetration test and UAT (month 8), M5 go-live (month 9).",
                     "Team: programme manager, architect, 4 engineers, 1 security lead and 1 compliance analyst. The proposed schedule exceeds the 6-month target in the RFP; compression is possible only by reducing the security gates."],
        "price": [["Item", "Cost (USD)"], ["Licences, 800 users, 3 years", "720,000"], ["Implementation services", "410,000"], ["Dedicated environment and key management", "95,000"], ["Training", "25,000"], ["Total (3 years)", "1,250,000"]],
        "assumptions": "Prices exclude taxes. Dedicated hosting is mandatory. Annual licence uplift of 5%. Any scope change is quoted separately.",
        "security": ["Certifications: ISO 27001, SOC 2 Type II, ISO 27701 and FedRAMP Moderate. Independent penetration tests twice a year with reports shared on request.",
                     "Controls: customer-managed keys, hardware security modules, mandatory multi-factor authentication, immutable audit logs retained 10 years, data residency selectable by country, and a 1-hour incident notification commitment."],
        "support": ["Business-hours support with a 4-hour response for severity 1. 24x7 support is available as a paid option. 99.9% uptime SLA.",
                    "Experience: 5 deployments, mostly in banking and healthcare. One reference is provided; others are subject to customer consent."],
    },
    "Vertex_Solutions": {
        "name": "Vertex Solutions",
        "summary": ["Vertex Solutions offers a feature-rich contract analytics platform with strong automation and an experienced engineering team. We understand the RFP asks for obligation tracking and ERP integration.",
                    "We believe our product is the most advanced technically, and we are competitively priced."],
        "solution": ["Architecture: cloud-native platform with built-in contract analytics, clause extraction and an open API. Prebuilt connectors exist for two ERP systems; the customer's ERP is not named in our response and will be assessed later.",
                     "Single sign-on via SAML and OIDC is supported. Scalability testing results are available but are not included in this document."],
        "timeline": ["Estimated duration 5 months. Milestones are listed at a high level: setup, configuration, integration, go-live.",
                     "Team structure: a delivery manager and engineers, with exact numbers to be confirmed. No risk plan is included in this response."],
        "price": [["Item", "Cost (USD)"], ["Licences, 800 users, 3 years", "430,000"], ["Implementation services", "190,000"], ["Total (3 years)", "620,000"]],
        "assumptions": "Data migration, training and support are not included in the figures above and will be priced separately.",
        "security": ["ISO 27001 certified. Data is encrypted in transit and at rest. SOC 2 is not yet held.",
                     "Privacy and auditability controls are described in our standard security whitepaper, which is not attached."],
        "support": ["Support hours and response times will be agreed in the contract. A community forum and online documentation are available.",
                    "Experience: 12 customers, mainly in software and media. Reference details are available on request."],
    },
}


def build_pdf(path: Path, data: dict) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=f"{data['name']} - RFP response",
                            leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50)
    story = [Paragraph(f"{data['name']} - Response to RFP-2026-017", styles["Title"]),
             Paragraph(REQUEST, styles["Italic"]), Spacer(1, 10)]

    def section(title, paragraphs):
        story.append(Paragraph(title, styles["Heading2"]))
        for text in paragraphs:
            story.extend([Paragraph(text, styles["BodyText"]), Spacer(1, 4)])

    section("1. Executive Summary and Understanding of the Requirement", data["summary"])
    section("2. Proposed Solution and Implementation Approach", data["solution"])
    section("3. Timeline, Team Structure and Milestones", data["timeline"])
    story.append(Paragraph("4. Price Table and Assumptions", styles["Heading2"]))
    table = Table(data["price"], colWidths=[320, 140])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                               ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                               ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    story.extend([table, Spacer(1, 6), Paragraph("Assumptions: " + data["assumptions"], styles["BodyText"])])
    story.append(PageBreak())
    section("5. Security, Compliance and Risk Controls", data["security"])
    section("6. Support Model, Relevant Experience and References", data["support"])
    doc.build(story)


def build_unreadable_pdf(path: Path) -> None:
    """A page with only a drawn shape and no text, like a scanned document."""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.rect(100, 400, 300, 200, fill=1)
    c.save()


def build_not_an_rfp_pdf(path: Path) -> None:
    """Readable text, but not a proposal: should be rejected by the template check."""
    styles = getSampleStyleSheet()
    body = ("Classic tomato soup. Chop the onions and garlic, then soften them in olive oil for "
            "ten minutes. Add the tomatoes, basil and stock, and simmer gently until thick. "
            "Blend until smooth and season with salt and pepper. Serve hot with fresh bread and a "
            "drizzle of cream. Leftovers keep in the fridge for three days and freeze well.")
    SimpleDocTemplate(str(path), pagesize=A4).build([
        Paragraph("Grandma's soup recipes", styles["Title"]), Paragraph(body, styles["BodyText"])])


def build_partial_pdf(path: Path) -> None:
    """Only three of the six expected sections: accepted with a warning."""
    styles = getSampleStyleSheet()
    story = [Paragraph("Partial Co - Response to RFP-2026-017", styles["Title"])]
    for title, text in [
        ("Executive Summary", "Partial Co is a small consultancy that wants to help the buyer manage contracts "
                              "more effectively. We understand the requirement for a contract platform."),
        ("Price Table", "Total price for 3 years is 500,000 USD including licences and services. "
                        "Prices exclude taxes and the cost of any additional integrations."),
        ("Security", "We use encrypted storage and follow common security practice. A formal compliance "
                     "programme is being introduced this year and details will follow.")]:
        story += [Paragraph(title, styles["Heading2"]), Paragraph(text * 2, styles["BodyText"])]
    SimpleDocTemplate(str(path), pagesize=A4).build(story)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    ERR.mkdir(parents=True, exist_ok=True)
    for stem, data in SUPPLIERS.items():
        build_pdf(OUT / f"{stem}.pdf", data)
        print("wrote", OUT / f"{stem}.pdf")
    build_unreadable_pdf(ERR / "Scanned_No_Text.pdf")
    print("wrote", ERR / "Scanned_No_Text.pdf")
    build_not_an_rfp_pdf(ERR / "Not_An_RFP.pdf")
    build_partial_pdf(ERR / "Partial_Proposal.pdf")
    (ERR / "Not_Really_A_PDF.pdf").write_text("This is plain text renamed to .pdf, not a real PDF file.\n")
    print("wrote 3 more error-case files in", ERR)
