# LOW-COST MAINTENANCE MANAGEMENT SOFTWARE FOR SMALL SCALE MINES
## Project Review Report (Six-Chapter Format)

Prepared by: **[Student Name / Team Name]**  
Register No.: **[Register Number]**  
Department: **[Department Name]**  
Institution: **[College / University Name]**  
Project Site: **SRC Mines, Cheyyar**  
Date: **[Submission Date]**

---

## Table of Contents
1. Chapter 1 - Introduction  
2. Chapter 2 - Literature Review  
3. Chapter 3 - Small-Scale Mine Operations and Maintenance Theory  
4. Chapter 4 - Preventive Maintenance, Alerting, and Decision Theory  
5. Chapter 5 - Software System Design and Implementation  
6. Chapter 6 - Validation, Deployment, and Final Outcomes  

---

## Chapter 1 - Introduction

### 1.1 Background
Mining and quarry operations depend on continuous machine availability. In stone crushing plants, unplanned breakdowns in jaw crushers, cone crushers, vibrating screens, and related conveyors directly reduce production, increase maintenance cost, and create safety risks. Traditional paper-based maintenance tracking is often delayed, inconsistent, and difficult to audit.

To address this, the project develops a **Low-Cost Maintenance Management Software for Small Scale Mines** that converts maintenance management from reactive to proactive. The system allows operators and supervisors to record machine details, maintenance due dates, running hours, and checklist status, then automatically generates alerts and maintenance actions.

### 1.2 Problem Statement
Existing field practice faces these gaps:
- Maintenance reminders are manual and frequently missed.
- Running-hour-based maintenance is not consistently tracked.
- Escalation of pending issues to supervisors/managers is delayed.
- Maintenance history and report generation are not standardized.
- Visibility of mine profile, operator compliance, and audit trails is limited.

### 1.3 Project Objectives
This project aims to:
- Build a centralized preventive maintenance application for mining machines.
- Trigger automatic alerts based on **date rules** and **hour rules**.
- Provide escalation flow (operator -> supervisor -> manager/admin).
- Track machine history, completion logs, and audit records.
- Generate professional reports (HTML, PDF, DOCX, CSV, XLSX).
- Support role-based control for admin and operator workflows.

### 1.4 Scope
In scope:
- Mine setup and mine profile management.
- Machine registry, due tracking, and maintenance history.
- Hour entry integration and runtime-based due logic.
- SMS alert automation and audit logs.
- Operator records with compliance dates and certificate attachment support.
- Background scheduler integration for automatic alert scanning.

Out of scope:
- Live PLC/SCADA sensor ingestion (future extension).
- Full ERP integration (SAP/Oracle).
- Native Android/iOS client (future extension).

### 1.5 Methodology
The solution follows an iterative engineering approach:
1. Domain requirement capture from crushing-plant workflow.
2. UI + workflow modeling for operations and maintenance teams.
3. Rule-based logic implementation for due and overdue states.
4. Alert automation with logging, deduplication, and escalation.
5. Validation through test cases, smoke runs, and scenario checks.

---

## Chapter 2 - Literature Review

### 2.1 Introduction to the Literature Review
The literature on maintenance management shows that industries with continuous equipment usage benefit significantly from planned maintenance systems rather than breakdown-driven repair practices. Research and industrial case studies commonly conclude that preventive maintenance improves equipment reliability, reduces downtime, and lowers the total cost of operation over time.

For small-scale mines, the literature is especially relevant because these operations often face financial limits, reduced staffing, and minimal digital infrastructure. This makes low-cost and easy-to-implement maintenance solutions more suitable than heavy enterprise maintenance platforms.

### 2.2 Maintenance Management Systems in Industry
Published work on maintenance management systems explains that maintenance performance improves when organizations move from manual registers to digital records. Common findings include:
- Better tracking of machine history
- Improved maintenance scheduling
- Faster identification of due and overdue tasks
- Easier generation of reports for management review
- Better coordination between operators and supervisors

However, many systems discussed in industrial literature are designed for large organizations and may not be practical for smaller mines because of higher cost, greater complexity, and infrastructure requirements.

### 2.3 Preventive Maintenance in Mining and Quarry Operations
Studies related to mining and quarry operations emphasize that crushers, screens, conveyors, and lubrication systems are critical equipment groups whose failure directly affects production. Literature in this area shows that:
- Wear parts must be monitored regularly
- Lubrication intervals are essential for equipment life
- Scheduled inspections reduce severe breakdowns
- Machine downtime has a direct impact on plant productivity

The reviewed theory strongly supports the idea that maintenance in mines must be planned around actual equipment conditions and operating schedules.

### 2.4 Use of Digital Alerts in Maintenance Systems
Modern literature on maintenance software highlights the importance of reminders and notification systems. Alerting mechanisms such as SMS, email, and dashboard warnings help maintenance teams respond before a due condition becomes a failure condition. Among these, SMS is considered highly practical for field environments because it:
- Reaches users immediately
- Does not require constant login to the application
- Works well in basic operational settings
- Supports fast escalation to supervisors and managers

This is highly relevant for small-scale mines where field response time is critical and advanced communication platforms may not be available.

### 2.5 Research Gap
Although many maintenance systems exist, the literature shows a gap in solutions specifically tailored for small-scale mines with low-cost constraints. Existing gaps include:
- Overdependence on expensive enterprise systems
- Limited support for simple runtime-based alerts
- Poor adaptation to mine-specific workflows
- Weak integration of operator communication and maintenance records
- Inadequate focus on low-cost deployable software for local use

### 2.6 Need for the Proposed Work
Based on the literature, there is a clear need for a practical software system that combines:
- Preventive maintenance planning
- Running-hour-based due logic
- Low-cost field communication
- Maintenance history and reporting
- User-friendly operation for small mine staff

Thus, the proposed project addresses an identified practical gap by designing a maintenance management solution specifically suited for small-scale mine environments.

---

## Chapter 3 - Small-Scale Mine Operations and Maintenance Theory

### 3.1 Nature of Small-Scale Mining Operations
Small-scale mines and quarries operate with limited capital, compact workforce structures, and high dependence on the availability of a few critical machines. Unlike large mining corporations, small-scale mines usually cannot afford complex enterprise maintenance platforms, large instrumentation systems, or dedicated reliability departments. As a result, maintenance planning is often handled manually through notebooks, spreadsheets, or verbal communication.

This creates a strong need for a low-cost digital system that is practical, easy to use, and capable of supporting field-level decision making without requiring expensive infrastructure.

### 3.2 Production Flow in Small-Scale Mines
In many small quarry and aggregate operations, the production cycle follows a simple but critical sequence:
1. Material extraction from the mine face
2. Loading and transport to the crusher feed point
3. Primary crushing
4. Secondary crushing or size reduction
5. Screening and product separation
6. Stockpiling and dispatch

Each stage depends on the availability of the previous stage. Therefore, a failure in one machine can affect the entire production chain. This makes maintenance management a production-support function rather than a separate administrative task.

### 3.3 Role of Maintenance in Small-Scale Mines
Maintenance in small-scale mines has three major objectives:
- To keep production equipment continuously available
- To reduce sudden machine failure and downtime
- To minimize repair cost by detecting problems before breakdown

Because budget and manpower are limited, maintenance must be economical, simple, and prioritized around the most critical equipment. In such environments, preventive action is more valuable than costly corrective repairs.

### 3.4 Typical Machines Requiring Maintenance Control
The most common equipment that demands routine maintenance monitoring in small-scale mines includes:
- Jaw crushers
- Cone crushers
- Vibrating screens
- Conveyor belts
- Feed hoppers
- Motors, pumps, and lubrication units

These machines experience wear due to dust, vibration, abrasiveness of rock, impact loading, and continuous operation. If maintenance is delayed, the mine may experience reduced production, low product quality, increased fuel or power usage, and unsafe operating conditions.

### 3.5 Challenges of Traditional Maintenance Practice
Traditional maintenance management in small mines usually suffers from the following problems:
- No proper record of last maintenance date
- Running hours are not tracked accurately
- Wear parts are replaced only after visible failure
- Reminders depend on memory rather than system logic
- Supervisors receive information late
- Maintenance history is difficult to review during inspections or audits

Because of these limitations, small mines need a software model that remains low in cost but high in usefulness.

### 3.6 Need for a Low-Cost Maintenance Management Software
A low-cost maintenance management system is important because it provides:
- Centralized machine data storage
- Maintenance due tracking by date and runtime
- Faster operator-to-supervisor communication
- Automatic alerts before due and overdue conditions
- Better documentation for review, reporting, and compliance

Thus, the theoretical foundation of this project lies in applying affordable digital control to improve equipment reliability and operational continuity in small-scale mining conditions.

---

## Chapter 4 - Preventive Maintenance, Alerting, and Decision Theory

### 4.1 Maintenance Strategies Relevant to the Project
Theoretical maintenance strategies used in industrial systems can be classified as:
- **Corrective maintenance**: maintenance performed after a failure occurs
- **Preventive maintenance**: maintenance carried out at planned time intervals
- **Predictive maintenance**: maintenance based on condition or risk indicators
- **Usage-based maintenance**: maintenance triggered after a machine reaches a specified runtime or work threshold

For small-scale mines, a low-cost system should mainly focus on **preventive maintenance** and **usage-based maintenance**, because these methods give strong results without requiring costly sensors or advanced infrastructure.

### 4.2 Preventive and Usage-Based Maintenance Theory
Preventive maintenance is the planned inspection, servicing, or replacement of machine parts before actual failure occurs. Its purpose is to reduce unplanned downtime and extend machine life. Usage-based maintenance is based on actual machine operation rather than only calendar dates.

Examples include:
- Jaw plate inspection every week
- Lubrication oil change after fixed hours
- Bearing inspection after fixed operating interval
- Belt alignment and tension check during routine shutdown

In mining machines, wear depends strongly on:
- Running hours
- Load handled
- Rock hardness
- Abrasiveness
- Operating conditions

Therefore, a machine may need maintenance not only after a date interval but after crossing a usage threshold such as 250, 500, or 1000 hours.

### 4.3 Maintenance Status Classification Theory
For effective maintenance control, machine condition must be translated into understandable status levels. A practical classification is:
- **Normal**: machine is healthy and not close to maintenance threshold
- **Maintenance**: machine is approaching a due point and requires preparation
- **Due**: maintenance should be carried out immediately
- **Overdue**: scheduled maintenance has been missed beyond allowable limit

This classification helps operators and supervisors take action quickly. In software terms, it also provides a clear basis for color badges, dashboard panels, and alert routing.

### 4.4 Alert and Escalation Theory
An alert system is effective only when it sends the right information to the right person at the right time. In maintenance management, alert theory involves:
- Reminder before due date
- Due notice on scheduled date or hour
- Escalation when action is delayed
- Stop of reminders after task completion

In a low-cost software environment, SMS is a strong alerting medium because:
- It does not require constant app usage
- It reaches field staff quickly
- It works well in low digital infrastructure environments
- It creates immediate attention for due and overdue tasks

### 4.5 Rule, Audit, and Reporting Theory
A rule engine maps conditions to actions. For example:
- IF status is overdue and risk is high, then raise a critical alert
- IF days to due is less than threshold, then raise a warning alert

For review and governance, each automated action must produce traceable records:
- What was triggered
- Why it was triggered
- Who was notified
- When it occurred
- Outcome or result

Maintenance reporting is also a decision-support activity. It supports daily action planning, overdue prioritization, completion monitoring, and management review meetings. Hence report generation and audit history are core theoretical needs, not just optional outputs.

### 4.6 Operator Compliance Theory
Maintenance systems in mines should not only track machines but also human readiness. Operators play a critical role in equipment safety and reliability. Hence, operator records should include:
- Phone number for communication
- License or registration validity
- Medical certificate validity
- Experience start date

This theory supports the software extension where operator compliance dates can also generate renewal alerts.

### 4.7 Relevance to the Proposed Software
The software developed in this project applies maintenance theory in a practical low-cost form by combining:
- Date-based preventive planning
- Hour-based maintenance triggering
- Automatic SMS reminders
- Escalation logic
- Machine history logging
- Rule-based alert decisions
- Report generation for review and documentation

Therefore, Chapter 4 provides the theoretical justification for why the proposed software is appropriate, economical, and useful for small-scale mining environments.

---

## Chapter 5 - Software System Design and Implementation

### 5.1 Technology Stack
Current implementation uses:
- **Python**
- **CustomTkinter** desktop UI
- JSON/file-backed data stores (with optional DB modules)
- SMS integration (Fast2SMS/Twilio paths)
- Optional async API/server mode

### 5.2 Application Navigation (Task-Based)
The UI follows a workflow-oriented sidebar:
- Dashboard
- Mine Details
- Checklist
- Hour Entry
- Machines
- Plant Maintenance
- Schedules
- Alerts
- Rule Engine
- Operators / Operator Records
- Maintenance History
- Reports
- Settings

This supports field usage sequence instead of feature-first complexity.

### 5.3 Core Functional Modules
1. **Mine Setup Module**  
Captures mine/company profile, quarry type, lease area, address, map link, branding context.

2. **Machine Management Module**  
User-managed machine list (no forced defaults), due date/hour fields, machine status badges.

3. **Checklist and Hour Entry**  
Captures recurring checks and runtime entries that feed maintenance calculations.

4. **Alert Engine Module**  
Automatic scan computes machine status and sends SMS using configured rules and contacts.

5. **Rule Engine + Predictive Layer**  
Evaluates customizable conditions and raises priority signals for high-risk states.

6. **Operator Records Module**  
Maintains operator phone/compliance fields and supports certificate metadata/image attachment constraints.

7. **Reports Module**  
Generates clean reports from live user data in HTML/PDF/DOCX/CSV/XLSX formats.

### 5.4 Data Design
The system persists operational data through app data files, including:
- `machines.json`
- `operators.json`
- `schedules.json`
- `machine_alert_state.json`
- `alert`/audit log datasets
- report delivery state files

Design principle:
- User-entered data is the source of truth.
- Reports and dashboards read from the same persisted records for consistency.

### 5.5 Automation Flow
Automated cycle:
1. Load settings and recipient mappings.
2. Evaluate machine status (date + hours).
3. Apply alert, dedup, escalation, and rule logic.
4. Send SMS and write audit/incident logs.
5. Optionally generate scheduled report and email delivery.

### 5.6 Role and Control
Role-based behavior is implemented in UI/settings paths:
- Admin-focused controls for automation, escalation, and backup settings.
- Operator-facing flows for entry, checklist, and day-to-day operations.

### 5.7 Professional UI/UX Features Implemented
- Task-based navigation ordering
- Section gradients and visual differentiation
- Active card/sidebar glow cues
- Scrollable large-page layouts
- Report pages designed for clean export readability

---

## Chapter 6 - Validation, Deployment, and Final Outcomes

### 6.1 Functional Validation Summary
The project includes:
- Unit/integration-style tests across authentication, maintenance sync, scheduling logic, and other modules.
- Runtime smoke validation for service initialization and report/alert pathways.
- UI workflow verification for major sidebar flows and export operations.

### 6.2 Observed Engineering Outcomes
Validated outcomes include:
- Automated machine due detection from date and runtime fields.
- Alert generation to configured recipients with escalation capability.
- Maintenance history logging and report-ready dataset preparation.
- Multi-format report generation for review/audit.
- Background execution support via task-based runner strategy.

### 6.3 Deployment Model
Target deployment modes:
1. Desktop execution (operator/admin workstation)
2. Packaged Windows application (portable/installer path)
3. Background scheduled run for automatic alert processing when UI is closed

### 6.4 Limitations
- End-to-end automation quality depends on correct field data entry.
- Gateway/network constraints can affect SMS and email delivery reliability.
- Environment-level OS permission constraints may affect some automated test temp paths.

### 6.5 Future Enhancements
Recommended next upgrades:
- SCADA/PLC sensor integration for real-time telemetry.
- Advanced predictive models from historical failures.
- Spare consumption forecasting and auto procurement triggers.
- Mobile companion app for supervisors.
- Digital signature workflow for maintenance closure approvals.

### 6.6 Final Conclusion
This project successfully transforms mine maintenance operations from manual tracking to a structured, alert-driven digital workflow. The system integrates plant-domain maintenance theory with practical software automation, enabling timely interventions, better compliance, improved reporting, and clearer accountability across operator, supervisor, and admin levels.

For project review purposes, the six-chapter structure demonstrates complete coverage of:
- industrial context,
- theoretical foundation,
- software architecture,
- implementation quality,
- and deployment readiness.

---

## Suggested Annexures (Optional for Submission)
- Annexure A: Screenshot set (Login, Mine Details, Dashboard, Alerts, Reports)
- Annexure B: Data dictionary (machines/operators/schedules/alerts)
- Annexure C: Sample generated report output
- Annexure D: Test scenario checklist
