In BPMN (Business Process Model and Notation), breaking down a large diagram into multiple pages or hierarchical layers relies on a few key concepts, depending on how you structure them:

## 1. Sub-processes (Collapsed Sub-processes)

When you hide a chunk of detailed work inside a single activity box on your main page, that box is called a **Collapsed Sub-process**. 

* On the high-level parent sheet, it appears as a rounded rectangle with a small plus sign (**[+]**) at the bottom.
* The detailed workflow behind that box is drawn on a separate sheet (or drill-down view), which is called the **Child Process** or **Sub-process diagram**.

---

## 2. Call Activities (Global Processes)

If the broken-out section is a standard process reused across multiple different diagrams (like an "Verify Identity" or "Process Payment" workflow), BPMN calls it a **Call Activity** (or Reusable Sub-process). 

* On the main sheet, it looks like a sub-process box, but with a **thick border**.
* The referenced diagram on its own sheet is a **Global Process**.

---

## 3. Link Events (Off-Page Connectors)

If you aren't creating a hierarchy (parent/child) and just need to split a long, linear flow across page breaks—like an off-page connector in traditional flowcharting—you use **Link Intermediate Events**.

* A **Catching Link Event** and **Throwing Link Event** act as matching paired nodes (e.g., labeled "Go to Page 2 / Marker A") to jump the sequence flow across sheets without cluttering the page with long lines.

---

### Summary Table

| What You're Doing | Element on Main Sheet | Name of the Separate Diagram |
| :--- | :--- | :--- |
| **Hiding detail inside a box** | Collapsed Sub-process (`[+]` icon) | Child Process / Sub-process |
| **Referencing a reusable process** | Call Activity (Thick border) | Global Process |
| **Jumping across pages linearly** | Link Throw Event | Link Catch Event (on new page) |