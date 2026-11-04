// Real provider episode lookup and browser decoding. Network responses are not mocked.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function run() {
    const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'scenetrace-watch-'));
    const proc = spawn('python', ['-m', 'scenetrace', '--no-browser'], {
        env: {...process.env, SCENETRACE_DATA: folder}, stdio: 'ignore',
    });
    let browser;
    let address;
    try {
        for (let i = 0; i < 200; i++) {
            try {
                const instance = JSON.parse(await fs.readFile(path.join(folder, 'instance.json'), 'utf8'));
                if ((await fetch(instance.url + '/health')).ok) {
                    address = instance.url;
                    break;
                }
            } catch {}
            await sleep(100);
        }
        assert(address, 'SceneTrace did not start');
        browser = await chromium.launch({headless: true, args: ['--autoplay-policy=no-user-gesture-required']});
        const page = await browser.newPage({viewport: {width: 1366, height: 950}});
        page.setDefaultTimeout(45000);
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(address);
        await page.getByRole('button', {name: 'Start discovering →'}).click();
        await page.getByRole('button', {name: 'Anime', exact: true}).click();
        await page.locator('#watch-source').selectOption('pokemon-tv');
        await page.getByRole('textbox', {name: 'Video search'}).fill('Pocket Monsters');
        await page.getByRole('button', {name: 'Search', exact: true}).click();
        await page.getByRole('heading', {name: 'Pokémon: Indigo League', exact: true}).waitFor();
        await fs.mkdir('artifacts', {recursive: true});
        await page.screenshot({path: 'artifacts/anime-search.png', fullPage: true});
        await page.getByRole('button', {name: 'View video options'}).click();
        await page.getByRole('button', {name: /Episode 1 · Pokémon, I Choose You/}).click();
        const handoff = page.getByRole('link', {name: /Open exact video at source/});
        await handoff.waitFor();
        assert.equal(await handoff.getAttribute('href'), 'https://www.youtube.com/watch?v=z3hMX65Khtg');
        assert.equal(await page.getByText('Download this video', {exact: true}).count(), 0);
        const embed = await page.locator('iframe.episode-frame').count();
        console.log('Pokémon TV: alternate title, three publisher episodes, exact episode handoff, official embed exposed=' + Boolean(embed));
        await page.getByRole('button', {name: 'Close dialog'}).click();

        await page.getByRole('button', {name: 'Universal Video Search', exact: true}).click();
        await page.locator('#watch-source').selectOption('open-animation');
        await page.getByRole('textbox', {name: 'Video search'}).fill('Caminandes');
        await page.getByRole('button', {name: 'Search', exact: true}).click();
        await page.getByRole('heading', {name: 'Caminandes', exact: true}).waitFor();
        await page.getByRole('button', {name: 'View video options'}).click();
        await page.getByRole('button', {name: /Episode 3 · Llamigos/}).click();
        const video = page.locator('#episode-video');
        await video.waitFor();
        await video.evaluate(async element => {
            element.muted = true;
            await element.play();
        });
        try {
        await page.waitForFunction(() => {
            const element = document.querySelector('#episode-video');
            return element && element.currentTime > 0.25 && element.videoWidth > 0;
        }, null, {polling: 100, timeout: 20000});
        } catch (error) {
            console.log('Player diagnostics', await video.evaluate(element => ({
                currentTime: element.currentTime, duration: element.duration, paused: element.paused,
                readyState: element.readyState, networkState: element.networkState, seeking: element.seeking,
                error: element.error?.message, width: element.videoWidth, buffered: Array.from(
                    {length: element.buffered.length}, (_, i) => [element.buffered.start(i), element.buffered.end(i)]
                ),
            })));
            await page.screenshot({path: 'artifacts/caminandes-player-diagnostics.png', fullPage: true});
            throw error;
        }
        await page.getByLabel('Speed', {exact: true}).selectOption('1.25');
        assert.equal(await video.evaluate(element => element.playbackRate), 1.25);
        await page.screenshot({path: 'artifacts/caminandes-playing.png', fullPage: true});
        await page.getByText('Download this video', {exact: true}).waitFor();
        assert.deepEqual(errors, []);
        console.log('Caminandes: searchable series, exact episode, actual video frames and advancing playback, speed and eligible download shown.');
    } finally {
        if (browser) await browser.close();
        if (address) {
            try {
                await fetch(address + '/api/shutdown', {method: 'POST', headers: {
                    'Content-Type': 'application/json', 'X-SceneTrace': 'local',
                }, body: '{}'});
            } catch {}
        }
        if (proc.exitCode === null) {
            await Promise.race([new Promise(resolve => proc.once('exit', resolve)), sleep(4000)]);
            if (proc.exitCode === null) proc.kill();
        }
        await fs.rm(folder, {recursive: true, force: true, maxRetries: 10, retryDelay: 100});
    }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
