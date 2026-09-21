# KONE SalesNXT User Manual

## 1. About the application

KONE SalesNXT helps sales teams create elevator modernization visualisations
for customer presentations.

A typical workflow is:

1. Create or open a project.
2. Upload an elevator image.
3. Select the elevator components to visualise.
4. Let AI place the selected components.
5. Review and correct the placement if needed.
6. Generate an optional video.
7. Download the final images, annotations, video, or brochure.

The application saves each workflow inside its project so it can be reopened
later.

## 2. Before you begin

For the best result, prepare:

- A clear JPG or PNG image of the elevator, lobby, or cabin.
- A front-facing or reasonably straight image.
- Good lighting and enough resolution to see the elevator area clearly.
- The component choices you want to show the customer.
- Optional customer or project text for the brochure.

The input image should clearly show the area where the selected component will
be placed. Avoid heavily blurred, very dark, or tightly cropped images.

## 3. Sign in or create an account

1. Open the SalesNXT application.
2. Select **Sign in** if you already have an account.
3. Enter your work email and password.
4. Select **Sign in**.

To create a new account:

1. Open the sign-up page provided by your deployment.
2. Enter your full name and work email.
3. Create a password with at least 8 characters.
4. Confirm the password.
5. Select **Create account**.

After successful sign-in, the application opens the **My Projects** page.

> **Screenshot slot:** Capture the sign-in page as
> docs/screenshots/01-sign-in.png.

## 4. Projects

The **My Projects** page is the starting point for all visualisation work.

### Create a project

1. Select **New Project**.
2. Enter a project name between 2 and 80 characters.
3. Select **Create**.
4. The new project opens automatically.

Each project contains its own uploaded image, component selections, generated
previews, videos, and brochure content.

### Open, rename, or delete a project

- Select a project card to continue working.
- Open the three-dot menu on a project card to rename it.
- Use the same menu to delete a project and its saved data.
- Use **Back to Projects** to return to the project list.

> **Screenshot slot:** Capture the project list showing the **New Project**
> button and one project card as docs/screenshots/02-projects.png.

## 5. The visualisation workflow

The workflow uses six steps shown in the progress navigation:

| Step | Name | Purpose |
|---:|---|---|
| 1 | Upload | Add and validate the source image |
| 2 | Components | Choose the environment and components |
| 3 | Preview | Generate and review the AI preview |
| 4 | Repin | Correct component placement when required |
| 5 | Video | Generate an optional motion or door video |
| 6 | Download | Download final outputs and open brochure tools |

Step 4 is optional when the AI placement already looks correct.

### Step 1 — Upload an image

1. Open a project.
2. Select the upload area.
3. Choose a JPG or PNG image.
4. Review the uploaded image.
5. Select **Check**.
6. Wait for the image check to pass.
7. Select **Continue**.

The image check confirms that the uploaded image is suitable for the
visualisation workflow. If it fails, upload a clearer or better-framed image.

You can click the uploaded image again to replace it.

> **Screenshot slot:** Capture a valid uploaded image with the validation
> result visible as docs/screenshots/03-upload-validation.png.

### Step 2 — Select components

First select the environment:

- **Car** — for components inside the elevator cabin.
- **Lobby** — for landing or building-lobby components.

Then select the components to visualise. Depending on the available catalogue,
components can include:

- Elevator interior
- Car Operating Panel (COP)
- Landing Call Indicator (LCI)
- DCS1020 or destination-control components
- Elevator door

Use the search field to find an option quickly. Select a component card to add
it to the workflow. Select the preview icon on a card to view a larger image.

The workflow supports up to five selected components. The interface also applies
the component rules shown on screen, including limits for structure, DCS1020,
and KDS selections.

To change a selection:

- Select another variant in the catalogue.
- Select the selected component name to edit it.
- Select the remove icon to remove it.

Select **Continue** when at least one environment and one component are selected.

> **Screenshot slot:** Capture the environment selector, component catalogue,
> search field, and selected-components area as
> docs/screenshots/04-component-selection.png.

#### Component visual examples

These are real component assets included in the application:

![Example Car Operating Panel component](Frontend/kone-ui-master/public/components/cop/Flush%20COP.png)

*Example: Flush Car Operating Panel option.*

![Example elevator interior component](Frontend/kone-ui-master/public/components/elevator-interior/Art%20Deco.png)

*Example: Art Deco elevator interior option.*

### Step 3 — Generate and review the preview

After continuing from component selection, the application starts the AI
placement workflow.

The system uses the source image, selected environment, and selected components
to estimate where each component belongs. While processing, the screen shows
that the final preview is being generated.

When the preview is ready:

1. Review the generated image.
2. Check that each selected component is present.
3. Check the scale, alignment, lighting, and perspective.
4. Confirm that the background and elevator geometry still look natural.
5. Continue to the video step, or open Repin if a correction is needed.

The screen shows how many components are placed. All components should be
reviewed before continuing.

> **Screenshot slot:** Capture the generated preview and AI placement status as
> docs/screenshots/05-ai-preview.png.

### Step 4 — Repin and correct placement

Use Repin when a component is missing, too large, too small, or positioned
incorrectly.

1. Select the component you want to correct.
2. Drag the component to the correct location.
3. Resize or adjust its perspective using the available handles.
4. Use the eraser controls when part of the generated component needs to be
   removed or cleaned.
5. Review the other component layers.
6. Save or continue when the placement looks correct.

Use small adjustments first. Large changes to size or perspective can make a
component look less natural.

If the AI result is already correct, skip this step and continue to Video.

> **Screenshot slot:** Capture the Repin canvas with a selected component and its
> adjustment controls as docs/screenshots/06-repin.png.

### Step 5 — Generate a video

Video generation is optional. A preview image must be available before a video
can be generated.

Choose a motion style:

- **Zoom In** — slowly moves toward the visualised elevator.
- **Pan** — moves horizontally across the scene.
- **Door Functionality** — creates an elevator door movement sequence when the
  required video service and source assets are available.

Choose a quality:

- 360p
- 480p
- 720p
- 1080p

Then:

1. Select **Generate Preview**.
2. Wait while the video is generated.
3. Play the video in the preview panel.
4. Change the motion style or quality and generate again if required.
5. Select **Continue** when the result is ready.

If a video is not required, select **Skip video generation**. The application
will continue to the download step using the generated image.

During generation, signed-in users can select **Cancel** if the process needs
to be stopped.

> **Screenshot slot:** Capture the Video Settings screen with motion and quality
> options visible as docs/screenshots/07-video-settings.png.

### Step 6 — Download outputs

The **Render & Download** screen prepares the final files.

Available outputs may include:

- Final visualisation image
- Annotated image showing component labels or placement
- Generated video
- Client brochure

To download an output:

1. Wait for rendering to finish.
2. Select the required output.
3. Select **Download**.
4. Save the file to the desired location.

Use the annotated image when presenting component locations internally. Use the
clean final image for a customer-facing presentation.

Select **Generate Brochure** to open the brochure workflow.

> **Screenshot slot:** Capture the Render & Download page with the output cards
> visible as docs/screenshots/08-downloads.png.

## 6. Create a client brochure

The brochure editor lets you add customer-facing text to the project.

The available sections are:

- Visualization Overview
- Competitor Comparison
- Unique Selling Points (U.S.P.)
- Customer Benefits (X.Y.Z.)
- Additional Notes (A.B.C.)

For each section:

1. Select the section to expand it.
2. Enter or edit the text.
3. Select **Done** to save that section.
4. Repeat until the required sections are complete.
5. Review the progress indicator at the top of the page.
6. Use the available export action to download the brochure.

The brochure can also use the selected component scope to describe areas such
as the COP, LCI, elevator interior, and door modernization.

> **Screenshot slot:** Capture the brochure editor with its progress indicator
> and editable sections as docs/screenshots/09-brochure.png.

## 7. Common workflows

### A. Create a quick image visualisation

1. Sign in.
2. Create a new project.
3. Upload a clear elevator image.
4. Validate the image.
5. Select Car or Lobby.
6. Select one or more components.
7. Continue to generate the AI preview.
8. Review the preview.
9. Skip video generation.
10. Download the final image.

### B. Compare different component options

1. Create or open a project.
2. Upload and validate the source image.
3. Select the required environment.
4. Select a component category.
5. Preview one catalogue option.
6. Select the option and continue.
7. Review the AI preview.
8. Return to Components if another variant is needed.
9. Generate a new preview.
10. Download the preferred version.

### C. Prepare a video walkthrough

1. Complete the Upload, Components, and Preview steps.
2. Correct the placement in Repin if needed.
3. Open Video Settings.
4. Choose Zoom In, Pan, or Door Functionality.
5. Select the required quality.
6. Generate the video preview.
7. Review the video.
8. Continue to Download.
9. Download the video and final image.

### D. Prepare a customer presentation package

1. Complete the image visualisation workflow.
2. Generate a video if required.
3. Download the clean final image.
4. Download the annotated image for internal reference.
5. Open the brochure editor.
6. Complete the relevant brochure sections.
7. Review the generated brochure.
8. Export the brochure for the customer presentation.

## 8. FAQs

### What image formats are supported?

The visualisation upload accepts JPG and PNG images. The brochure page can also
accept a PDF tender document when that option is available in the deployment.

### How many components can I select?

The workflow supports up to five selected components. Additional rules for
structure, DCS1020, and KDS combinations are shown in the Components step.

### Does AI place every component perfectly?

AI provides the first placement automatically, but every result should be
reviewed. Use Repin to correct position, scale, perspective, or unwanted
areas.

### Can I generate a video without generating an image preview?

No. A generated image preview is required before video generation.

### Can I skip video generation?

Yes. Select **Skip video generation** on the Video Settings screen to continue
to the download step with the image output.

### Which video quality should I choose?

Use 720p for a good balance of quality and processing time. Use 1080p when the
video will be shown on a large display and longer processing time is acceptable.
Use 360p or 480p for quick previews.

### Can I change a project after creating it?

Yes. Open the project and continue the workflow. You can also rename or delete
the project from the project menu.

### What happens if I leave before finishing?

Signed-in users can reopen the project and continue from its saved workflow
step. If the application is being used in a temporary guest session, work may
only be available for that browser session.

### Can I generate a brochure as a guest?

Brochure generation may require a signed-in account. Sign in before opening the
brochure workflow if the application displays that restriction.

### Where are my downloaded files?

The browser saves downloaded files according to its normal download settings.
Check the browser Downloads folder if no save dialog appears.

## 9. Troubleshooting

### The Continue button is disabled on Upload

- Confirm that a JPG or PNG image has been selected.
- Wait for the validation step to finish.
- If validation fails, upload a clearer and better-lit elevator image.
- Try replacing the image instead of reusing a failed upload.

### The Continue button is disabled on Components

- Select either Car or Lobby.
- Select at least one component.
- Remove extra components if the selection limit has been reached.
- Clear the search field if no catalogue options are visible.

### The preview is taking a long time

AI processing can take longer for large images, multiple components, or busy
scenes. Keep the browser tab open and wait for the processing status to update.

If the preview does not complete:

1. Refresh the project.
2. Reopen the workflow.
3. Confirm that the AI backend is running.
4. Try a smaller or clearer input image.
5. Ask the system administrator to check the backend logs.

### Components are missing or misplaced

- Open Repin and check each selected component.
- Use the component list to select the missing layer.
- Move or resize the component manually.
- If the result is still incorrect, return to Components and try a more
  suitable component variant or a better source image.

### The generated image looks unnatural

Use an image with:

- Straight elevator geometry.
- Minimal motion blur.
- Even lighting.
- The full target wall or door area visible.
- No people or objects covering the placement area.

Then regenerate the preview and use Repin for final alignment.

### Video generation is stuck

- Confirm that the image preview is already available.
- Wait for the generation status to update.
- Check that the video service is running.
- Try a lower quality such as 480p or 720p.
- Use **Cancel** and generate again if the current job is not progressing.
- If video is not required, select **Skip video generation**.

### A downloaded file is missing

- Wait until the Render & Download page finishes rendering.
- Refresh the page and reopen the project.
- Check the browser download permissions.
- Check that pop-ups are allowed when opening the brochure workflow.
- Ask the administrator to verify the API output and storage folders.

### The project cannot be opened

- Select **Retry** if the error screen provides it.
- Return to **All Projects** and open the project again.
- Confirm that the API and database services are running.
- Sign out and sign in again if the session has expired.

### The application shows a blank page

- Refresh the browser.
- Clear cached site data if the problem continues.
- Confirm that the frontend API URL points to the correct environment.
- Check the browser developer console and contact the administrator with the
  error message.

## 10. Recommended screenshot set for the client handoff

For a polished client manual, capture these screens from the deployed
application at a consistent browser size, preferably 1440 × 900:

| File | Screen |
|---|---|
| 01-sign-in.png | Sign-in page |
| 02-projects.png | My Projects page |
| 03-upload-validation.png | Upload and validation |
| 04-component-selection.png | Environment and component catalogue |
| 05-ai-preview.png | Generated AI preview |
| 06-repin.png | Repin adjustment screen |
| 07-video-settings.png | Video settings |
| 08-downloads.png | Render and Download |
| 09-brochure.png | Sales Brochure editor |

Store the captures in docs/screenshots/ and replace the screenshot slots in
this manual with the final image links.
