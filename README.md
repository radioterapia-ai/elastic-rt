# Elastic RT

**Part of the Radioterapia.AI Local Suite. Elastic RT: what a deformable registration did between two series, and whether it was plausible in a patient — teaching and research material, not a medical device.**

`License: Apache-2.0` · `Component of: Radioterapia.AI Local Suite` · `Platform: Windows 10 and 11, 64-bit`

> **Teaching and research material. This is not a medical device.**
> It is **not** validated for clinical use, and it has no ANVISA registration,
> no CE mark and no FDA clearance. A fusion is an **unapproved suggestion**:
> checking the alignment in the region that matters for the decision is a
> physician's act, and no number here replaces that check. It does not
> propagate contours. Every structure in the suite is an unapproved
> suggestion; reviewing and approving it is a physician's act, in the
> planning system.

## What it does

A deformable fusion always produces a convincing image — including when it
folded the patient. Elastic RT registers two series of the same patient and
measures the deformation it produced, so that the image is never seen without
the evidence about the field behind it.

- **Series**: CT, MR or PET. Nothing is read when the screen opens: two
  cards, *Load the image to be deformed* and *Load the target image*, each
  open the Suite's series pop‑up and pick one series, from the local archive
  or from a folder you point to, read in the background by the Suite's
  reader, with the series appearing as they are found, a filter by the date
  of each series folder, the favourite folder's star and *Stop reading*; an
  empty field asks for a folder instead of reading the whole watched folder.
  *Fuse* is enabled only with both, and the fusion starts only on that
  click. It does not open `.zip` files (it counts them and says so).
- **Registration**: rigid first, then deformable, by a B‑spline — chosen
  because it *can* fold, so that the measurement has something to catch.
- **Measurement of the field**, following AAPM TG‑132: the Jacobian
  determinant (where it is zero or negative the field folded; very small or
  very large values flag compression and expansion), the round trip (the
  field is inverted and the residual of going and coming back is reported),
  and the displacement. Where one series has gas and the other has tissue at
  the same place (rectum, bowel), no deformation is physically right, and the
  report says where.
- **Views**: the fixed series, the rigid result, the fused image, a
  checkerboard of the rigid and of the elastic result, the difference, and the
  Jacobian and round‑trip maps, with the deformed grid over the image and the
  report beside it, with a verdict and its reasons.
- **The image and the report go together, and that is a lock**: a view that
  derives from the deformation is not served while its report does not exist.
- **Different patients alert, and do not block**: the PatientID of the two
  series is read only to compare them, inside the process; when they differ,
  an alert sits beside the *Fuse* button and goes into the report.

Every request of the screen has a time limit; when the app does not answer,
the screen says so and offers to try again.

## What it does not do

- **It does not propagate contours.** It shows and measures the deformation;
  it does not move a structure from one series to the other. A structure
  carried through a field nobody checked reaches the plan looking like a
  checked contour — exactly what TG‑132 exists to prevent. It writes no
  RTSTRUCT and no deformed series.
- It is not a second opinion against another program: the deformable field of
  other systems is rarely exported in an open format. What is measured is the
  transformation against itself.
- It does not detect or classify anything — it is image registration.
- **The thresholds are this application's**, not TG‑132's: TG‑132 asks for
  per‑case QA and recommends that each service set its own tolerance, and it
  publishes no universal threshold.

## What is ours, and what is not

No model and no weight: this module does not use AI. Registration, the field,
the Jacobian and the inversion use [SimpleITK][sitk] (Apache‑2.0), and the PNG
is written with `zlib`. The metrics follow AAPM TG‑132 (Brock et al., Med Phys
2017). These libraries are installed by the Suite's preparer and do not travel
in this repository.

## Privacy

Everything runs locally, and nothing is exported: the images are drawn on the
screen and not written anywhere. The two PatientIDs are compared inside the
server process; only the answer — same patient or not — reaches the screen.

## Part of the Local Suite

Elastic RT does not run on its own. The shared shell — the entrance page, the
menus, the twelve languages, the Terms and the Privacy Policy, the
configuration, the case archive, DICOM reading and search, the viewers and
the queue — lives in the [Suite][suite], and on the workstation the suite is
one program: one process, one port, one `app` folder, assembled by the
Suite's installer from the seven repositories.

To use it, install the Suite with its light installer, from the
[releases of drhenriquebraga/local-suite][rel] (the permanent link to the
newest one is [`RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip`][latest]);
requirements and installation are in the Suite README.

This repository has no build of its own. The Suite's packager
(`build/empacotar_instalador.py --dos-repositorios`) downloads each component
at the tag pinned in `build/componentes.lock.json`, checks the SHA‑256 of its
extracted tree against the lock and
assembles the installer — see *Build from source* in the Suite README.

## Running the batteries

The batteries (`tools/test_*.py`, listed in `componente.json`) run over
synthetic phantoms. **No patient data is used anywhere in this repository, and
none may be committed to it.**

1. Put the [Suite][suite] and the six component repositories side by side in
   one folder. Folder names do not matter: the Suite is the folder with
   `tools/_componentes.py`, and each component is found by its
   `componente.json` (or set `RADAI_COMPONENTES_DIR` to the folder that holds
   the components). The batteries import modules of the Suite and of the
   other components, so all seven are needed.
2. Create the Suite's development environment: a Python virtual environment
   in `.venv` at the Suite root, as its README describes.
3. Run every battery of this component:

   ```
   <suite>\.venv\Scripts\python.exe <suite>\tools\_componentes.py --verificar <this folder>
   ```

   or a single one, with `--rodar test_<name>.py`. Each battery ends with an
   `OK:` or a `FALHOU:` footer, and `--verificar` ends with how many failed.
   `verify.cmd`, in this folder, does the same in two clicks once
   `_python.txt` (ignored by Git) holds the path of that `python.exe`.

4. **Turn on the pre‑commit hook** (once per clone):
   `git config core.hooksPath .githooks`. It runs the Suite's
   patient‑data scan over what is staged and refuses the commit that
   carries DICOM (with or without extension), a medical volume or a run
   log — and refuses it too when the scan cannot run, without the Suite
   beside this folder or without Python.

## Reporting a problem

A problem that is not a vulnerability goes through
**[radioterapia.ai](https://radioterapia.ai)**. Include the Local Suite
version, the Windows version, the screen language and the step that
failed — and **never patient data**: no DICOM series, no screenshot of a
patient image, no log with a patient ID, a UID or a series path. A problem
reproduced with the synthetic phantoms of the batteries is the quickest to
fix.

## Security

Found something that exposes patient data or lets the program act where it
should not? **Do not report it in public.** Use GitHub's private
vulnerability reporting on this repository, described in
[SECURITY.md](SECURITY.md).

## Licence and name

The code is licensed under the [Apache License 2.0](LICENSE). As section 6
says, the licence grants no permission to use the trade names of the
Licensor — "Radioterapia.AI", "Local Suite" and "Elastic RT" included —
except as required to describe the origin of the work. A build you adapt is
yours: name it as yours.

| | Published code | A service's own build |
|---|---|---|
| What it is | Teaching and research material | An in‑house tool the service adapts, validates and registers in its own jurisdiction |
| Medical device? | **No.** Not validated for clinical use | Whatever that service's validation and registration make it |
| Who answers for it | Whoever downloads, modifies and deploys it answers for their own build, made with the Suite's build path | The service that deploys it |

Built by Dr. Henrique Braga, radiation oncologist —
**[radioterapia.ai](https://radioterapia.ai)**.

[sitk]: https://simpleitk.org
[suite]: https://github.com/drhenriquebraga/local-suite
[rel]: https://github.com/drhenriquebraga/local-suite/releases
[latest]: https://github.com/drhenriquebraga/local-suite/releases/latest/download/RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip
