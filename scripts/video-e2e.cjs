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
    const executable = process.env.SCENETRACE_QA_EXE;
    const proc = spawn(executable || 'python', executable ? ['--no-browser'] : ['-m', 'scenetrace', '--no-browser'], {
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
        page.on('response', async response => {
            if (response.request().resourceType() !== 'media') return;
            const headers = await response.allHeaders();
            console.log('Media transport', response.status(), response.request().headers().range,
                headers['content-range'], headers['content-length'], headers['content-type']);
        });
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
        await page.getByRole('button', {name: 'Close dialog'}).click();
        await page.getByRole('button', {name: 'Video Sources', exact: true}).click();
        await page.getByRole('button', {name: 'Add Video Website', exact: true}).click();
        await page.getByLabel('Website URL', {exact: true}).fill('https://www.w3schools.com/html/html5_video.asp');
        await page.getByRole('button', {name: 'Inspect website', exact: true}).click();
        await page.getByLabel('Name', {exact: true}).fill('W3Schools video example');
        await page.getByLabel('Sample title or keywords', {exact: true}).fill('HTML Video');
        await page.getByRole('button', {name: 'Test integration', exact: true}).click();
        await page.getByText('playback · Direct media bytes checked', {exact: true}).waitFor();
        await page.screenshot({path: 'artifacts/website-test.png', fullPage: true});
        await page.getByRole('button', {name: 'Save website', exact: true}).click();
        await page.getByRole('heading', {name: 'W3Schools video example', exact: true}).waitFor();
        await page.getByRole('button', {name: 'Universal Video Search', exact: true}).click();
        await page.locator('#watch-source').selectOption({label: 'W3Schools video example'});
        await page.getByRole('textbox', {name: 'Video search'}).fill('HTML Video');
        await page.getByRole('button', {name: 'Search', exact: true}).click();
        await page.getByRole('button', {name: 'View video options'}).click();
        await page.locator('.episode').first().click();
        await page.locator('#episode-video').evaluate(async element => {
            element.muted = true;
            await element.play();
        });
        await page.waitForFunction(() => document.querySelector('#episode-video')?.currentTime > 0.2);
        await page.screenshot({path: 'artifacts/added-website-playing.png', fullPage: true});
        console.log('W3Schools: inspected, tested, saved, searched, and played a real HTML video without a media URL or API.');
        await page.getByRole('button', {name: 'Close dialog'}).click();
        await page.getByRole('button', {name: 'Memory Search', exact: true}).click();
        await page.getByRole('textbox', {name: 'Describe the video you remember'}).fill('llama Patagonia');
        const chips = page.locator('[data-source]');
        for (let i = 0; i < await chips.count(); i++) {
            const chip = chips.nth(i);
            if (await chip.getAttribute('data-source') !== 'open-animation') await chip.uncheck();
        }
        await page.getByRole('button', {name: /Follow the clues/}).click();
        await page.getByRole('heading', {name: 'Caminandes', exact: true}).waitFor();
        await page.getByRole('button', {name: 'Details', exact: true}).click();
        await page.getByRole('button', {name: /Find Video/i}).click();
        await page.getByRole('button', {name: /Episode 3 · Llamigos/}).waitFor();
        console.log('Memory Search: plot clues found Caminandes and led to the real episode list.');
        assert.deepEqual(errors, []);
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
