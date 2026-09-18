# River Run (TypeSafe)

A vertical-scrolling river shooter in Python with pygame-ce, plus an AI pilot that plays it using
[TypeSafe](https://typesafe.ai)'s System One model, Jev.

Inspired by the 1982 Atari 2600 game *River Raid* by Carol Shaw (Activision). This is an independent
project, not affiliated with or endorsed by Activision; all code, graphics and sounds are original.

The TypeSafe pilot playing in real time (with sound):

https://github.com/user-attachments/assets/7d0ddfc3-bd2c-40f6-bd0c-67bf818aec0b

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m river_run            # --seed N for a different river
```

## Controls

| Key | Action |
| --- | --- |
| Left / Right (A / D) | Steer |
| Up / Down (W / S) | Speed up / slow down |
| Space | Fire |
| P | Pause |
| M | Mute (or start with `--mute`) |
| Esc | Quit |

## Rules

- Fly up the river. Touching land, a ship, a helicopter, a jet or a standing bridge costs a life.
- Fuel drains constantly. Fly over a fuel depot to refill, or shoot it for points.
- Every section ends with a bridge. Destroying it makes the next section your respawn point.
- Points: ship 30, helicopter 60, fuel depot 80, jet 100, bridge 500. Extra life every 10,000.

## TypeSafe pilot

`typesafe_pilot/` lets TypeSafe's Jev model fly the plane. The screen is split into 20 lanes. Code measures
each lane the plane can reach (time to line up, open water ahead, objects in it or drifting into it); one
System One request per decision asks, in parallel, which lane to fly in, whether to fire, and how fast to go.
Code then turns the answers into controls.

On screen, white corner brackets mark the plane, and the strip along the bottom of the river shows the
lanes: outlined is the plane's lane, filled is the chosen lane, and the tick below is the exact steering target.
The text at the top shows the chosen lane and its confidence, the fire probability, the speed and the request time.

### Setup

What you need to run the TypeSafe pilot:

| Requirement | Why | How |
| --- | --- | --- |
| Python 3.10+ | `typesafe-sdk` and `pygame-ce` need it | `python3 --version` |
| `typesafe-sdk` 0.6+ | Python client for the System One API | Installed by `requirements.txt` (see [Run](#run)) |
| A TypeSafe API key | Every decision is one System One request to Jev | Create one at [console.typesafe.ai](https://console.typesafe.ai) |
| Network access to `api.typesafe.ai` | Requests go to TypeSafe's hosted API | About 8 requests per second while playing in real time |
| `ffmpeg` (optional) | Only for `--record` | macOS: `brew install ffmpeg`; Debian/Ubuntu: `sudo apt install ffmpeg` |

1. Install the game and SDK:

   ```sh
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Set your API key in the shell you run the pilot from (add it to `~/.zshrc` or `~/.bashrc` to keep it):

   ```sh
   export TYPESAFE_API_KEY="your-key-here"
   ```

   Don't commit the key. If it's missing, the SDK raises `No API key was provided`; if it's wrong, the pilot exits with `TypeSafe rejected the API key`.

3. Check it works with a short run without a window:

   ```sh
   .venv/bin/python -m typesafe_pilot --headless --frames 600
   ```

The SDK uses Jev (`jev-latest`) at `https://api.typesafe.ai` by default. These optional environment
variables, read by `typesafe-sdk`, change that:

| Variable | Default | Meaning |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | (required) | Your API key. Not needed for `--human`. |
| `TYPESAFE_DEFAULT_MODEL` | `jev-latest` | The System One model to use. |
| `TYPESAFE_BASE_URL` | `https://api.typesafe.ai` | API root. |
| `TYPESAFE_LOG_LEVEL` | off | SDK logging, e.g. `debug`. |

### Running the pilot

```sh
.venv/bin/python -m typesafe_pilot                                  # watch it play in real time
.venv/bin/python -m typesafe_pilot --lockstep                       # game waits for each decision
.venv/bin/python -m typesafe_pilot --headless --frames 3000         # no window, prints stats
.venv/bin/python -m typesafe_pilot --record play.mp4 --seconds 60   # save a video with sound (needs ffmpeg)
.venv/bin/python -m typesafe_pilot --human                          # fly it yourself (no API key needed)
```

`--human` works with `--record` and `--seconds`, so you can record your own games the same way.

### Steering

How Jev's lane probabilities become a steering target. These flags work with every mode above.

| Flag | Default | Meaning |
| --- | --- | --- |
| `--steering top\|blend` | `blend` | `top`: fly to the single most likely lane. `blend`: group likely neighboring lanes into blocks and fly to the probability-weighted center of the chosen block. |
| `--block-score sum\|max` | `sum` | Blend: choose the block with the highest total probability (`sum`) or the one holding the most likely lane (`max`). |
| `--blend-min-prob P` | `0.1` | Blend: lanes below this probability split blocks. |
| `--dead-end-px N` | `250` | Blend: lanes with less open water than this (and under half the best lane's) split blocks, so the lanes in front of an island don't join the channels beside it. `0` turns it off. |

In real time, requests run back to back: about 8 per second at roughly 115 ms each.

## Code

- `river_run/game.py`: rules, no pygame. `Game.step(Action)` advances one frame and returns events;
  `Game.observation()` returns what the pilot can see as plain data, for automated players.
- `river_run/world.py`: river and object generation from a seed.
- `river_run/render.py`: drawing. `river_run/__main__.py`: keyboard play.

```sh
.venv/bin/python -m pytest
```

## Acknowledgments

Thank you to the team at [TypeSafe](https://typesafe.ai) ([@typesafe-ai](https://github.com/typesafe-ai) on GitHub)
for early access to the System One API and to Jev, the model flying the plane in this project.

- Website: [typesafe.ai](https://typesafe.ai)
- Documentation: [docs.typesafe.ai](https://docs.typesafe.ai)
- Python SDK: [typesafe-ai/typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python) ([`typesafe-sdk` on PyPI](https://pypi.org/project/typesafe-sdk/))
- Agent skill used while building this: [typesafe-ai/skills](https://github.com/typesafe-ai/skills)
- JavaScript SDK: [typesafe-ai/typesafe-sdk-js](https://github.com/typesafe-ai/typesafe-sdk-js)
- Follow TypeSafe: [LinkedIn](https://www.linkedin.com/company/typesafe-ai/) · [X @typesafeai](https://x.com/typesafeai)

This project is not affiliated with or endorsed by TypeSafe AI, Inc.; TypeSafe and Jev are their names.
The scores and latencies mentioned here come from a few of our own runs, not an official benchmark.

## License

MIT, see [LICENSE](LICENSE). The license covers this project's code; *River Raid* is a trademark of its owner.
