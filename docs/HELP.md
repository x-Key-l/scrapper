# SceneTrace owner guide

## Find an episode

Open **Anime**, type a title, and select **View video options** or **Find episodes**. A title from AniList may give you alternate names or exact episode links from an official provider. A connected video website can supply more matches. Pick an episode to load its player. If the player is unavailable, use **Open exact video at source**.

Try **Pocket Monsters** for the first three official Indigo League episodes. For an in-app video, search **Caminandes** in Universal Video Search and select **Llamigos**.

## Search a website you added

1. Open **Video Sources → Add Video Website**.
2. Paste the website, listing or feed URL and choose **Inspect website**.
3. Review the connection method. Use advanced fields for a documented query parameter, CSS selectors, a JSON mapping or an episode listing.
4. Enter a sample title and choose **Test integration**. Review the returned pages, playback and download status.
5. Save the tested configuration. Choose its name in Universal Video Search and search again.

**Find More Sources** lists available connectors. Add a Brave Search key in Settings if you want additional web candidates. Discovered sites remain unverified until tested.

## Download a video

Open a video with eligible files, expand **Download this video**, choose the format and destination, and confirm your authorization. Track or pause the transfer under **Downloads**. An interrupted transfer can resume when its host supports a byte range.

## Use a description

Open **Memory Search**, describe your remembered scene or plot, and open a match. Choose **Find Video** for source and episode options. More distinctive details and alternative titles can improve the match.

## Internet Archive certificate error

Open **Settings → Test Archive HTTPS**. SceneTrace uses Windows certificate trust and checks the server hostname. If Windows rejects the chain, compare the same Archive URL in Edge and check the PC clock. On a managed network, have the administrator confirm the certificate issuer used by the proxy or antivirus. The app reports the certificate error code when available.

TMDB's **Optional key needed** label means its catalog needs your own API Read Access Token. Playback from the built-in examples works without that key.
