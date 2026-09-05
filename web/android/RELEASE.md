# Android release build (Play Console)

How to produce a signed `.aab` and get it onto the Closed Testing track.
Everything here runs on a machine with Android Studio (Android SDK) and
**JDK 21** — Capacitor 8 compiles `:capacitor-android` at Java 21, so a
JDK 17 `JAVA_HOME` fails with `compileReleaseJavaWithJavac FAILED`. Run
the build with `JAVA_HOME=$(/usr/libexec/java_home -v 21)` if your shell
default isn't 21 (don't use Android Studio's bundled JBR — it's newer than
AGP expects). Bundles and `key.properties` are gitignored; the keystore
lives outside the repo.

Store-listing graphics (feature graphic, icon pointer) are in `store/`.

## One-time setup

### 1. Generate the upload key

Play App Signing is used, so this is only the **upload** key — Google holds
the real app-signing key, and a lost upload key is recoverable by asking
Google to reset it. Still, back this file and its password up (password
manager).

```sh
keytool -genkeypair -v \
  -keystore ~/keys/goodgorithm-upload-key.jks \
  -alias upload \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -storetype PKCS12
```

Answer the name/org prompts (any reasonable values). It asks for one
password (PKCS12 keystores use the same password for store and key).

### 2. Point the build at it

```sh
cp web/android/key.properties.example web/android/key.properties
```

Edit `web/android/key.properties`:

- `storeFile` — absolute path to the `.jks` above (e.g. `/Users/you/keys/goodgorithm-upload-key.jks`)
- `storePassword` / `keyPassword` — the password from step 1 (same value for both)
- `keyAlias` — `upload`

`key.properties` and `*.jks` are gitignored; never commit either.

## Build the bundle

From `web/`:

```sh
npm ci
npm run build:android        # tsc -b, vite build --mode release (production api), cap sync android
cd android
./gradlew bundleRelease
```

Output: `web/android/app/build/outputs/bundle/release/app-release.aab`.

`--mode release` bakes in `VITE_API_BASE_URL` from `web/.env.release`
(production `api/`). The bundle is signed with the upload key from
`key.properties`; if that file is missing the bundle builds unsigned and
Play will reject it.

## Play Console — first Closed Testing release

1. **Create app** — name `Goodgorithm`, default language, "App", "Free". App
   category: *News & Magazines* (closest fit).
2. **App signing** — accept the default: *Use Play App Signing*, let Google
   generate the app signing key. Your `app-release.aab` is the upload
   artifact.
3. **Testing → Closed testing** — create a track (the default `alpha` is
   fine). Create the tester list: an email list or a Google Group with the
   ≥12 testers. New personal accounts need 12+ testers opted in for 14
   continuous days before Production unlocks — that window is the alpha
   itself.
4. **Create release** on that track → upload `app-release.aab` → release
   name auto-fills to `0.1.0 (1)` → add brief release notes → review →
   roll out.
5. **Store listing (minimum to publish the track):**
   - Short description, full description
   - App icon (512×512), feature graphic (1024×500)
   - At least 2 phone screenshots (grab from a device/emulator running the
     release build)
   - **Privacy policy URL:** `https://goodgorithm.com/privacy`
6. **App content declarations** (all required before rollout):
   - **Data safety:** *No data collected. No data shared.* (see below)
   - **Content rating:** fill the IARC questionnaire — no violence, no
     user-generated-content interaction *within the app* (posts are
     read-only, link out), likely rates *Everyone / PEGI 3*
   - **Target audience:** 18+ (feed content isn't curated for minors)
   - **Ads:** *No, this app does not contain ads*
   - **Government app / financial features / health:** No
7. Once the track shows *Available to testers*, share the **opt-in URL**
   with the tester list. Testers must accept the invite, then install from
   the Play link (not sideload).

### Data safety answers

The app has no account and no analytics/tracking SDKs. On the Data safety
form:

- *Does your app collect or share any of the required user data types?* →
  **No**
- *Is all of the user data encrypted in transit?* → **Yes** (HTTPS only)
- *Do you provide a way for users to request that their data is deleted?* →
  N/A / not applicable (no data is collected)

Local storage (feed position, display prefs) stays on device and is not
"collected" per Play's definition. Post images/video load directly from
Bluesky/Mastodon CDNs — disclosed in the privacy policy; not app-collected
data.

## Subsequent builds

Bump both in `web/android/app/build.gradle`:

- `versionCode` — integer, strictly increasing (2, 3, …); Play rejects a
  reused value
- `versionName` — human string (`0.1.1`, `0.2.0`, …); keep it in step with
  `web/package.json`

Then `npm run build:android && (cd android && ./gradlew bundleRelease)` and
upload the new `.aab` to the track.

## Cutting a new store build — the regression guards

The shipped app is frozen (no hotfix path), so CI holds `production` to what
the *current* store build expects:

- `.github/workflows/android-build.yml` — builds an unsigned `.aab` on every
  `web/**` change, so a dep/Capacitor/gradle break is caught before the next
  release.
- `api/tests/android-contract.test.ts` + `api/tests/contracts/android-feed-contract.ts`
  — asserts `/v1/feed`'s shape still matches what the frozen client
  (`web/src/api/client.ts`, which does no runtime validation) needs.
- `api/tests/cors.test.ts` — `/v1/feed` must keep allowing the native WebView
  origins (`https://localhost`, `capacitor://localhost`).

When you actually ship a new store build, re-anchor them:

1. Bump `versionCode` / `versionName` (above).
2. **Re-freeze the contract.** Diff `web/src/api/types.generated.ts` between
   the previous `android-vX` tag and the release commit. If the `/v1/feed`
   shape changed, hand-update `api/tests/contracts/android-feed-contract.ts`
   to the new shape and bump its `_meta` (`tag`, `versionCode`).
3. **Move the tag.** Delete + recreate `android-vX` (or create `android-vY`)
   on the new release commit; push it.
4. Build + upload as above.

A red `build-android-aab` or a failing contract/CORS test *after an
intentional* `api/` or Capacitor change means "cut a new store build and
re-freeze" — not "edit the test to pass".

## iOS

Deferred until the Apple Developer Program payment clears.
