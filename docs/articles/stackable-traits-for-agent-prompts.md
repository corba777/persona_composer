---
layout: default
title: "Stackable Traits for Agent Prompts"
description: "How a multiplayer game made me write a compiler for system prompts — modular Markdown, explicit conflict resolution, hashed manifests, and an optional compliance gate for third-party skills."
permalink: /articles/stackable-traits/
---

# Stackable Traits for Agent Prompts

*How a multiplayer game made me write a compiler for system prompts*

---

## The problem wasn't writing prompts

I was building a cooperative game where the party is made of LLM agents. Three player types — Hunter, Companion, Guard — each with its own behavior, its own priorities, its own way of reading a situation. Each of them already had a skill file, written and tested.

Then I wanted the agents to speak differently. Plain English for one playthrough, and — let's call it *Russian colloquial* — for another. That skill file existed too, written for something else entirely, and I wanted to reuse it as is.

Then there are the optional ones. Some scenarios put an agent in a position where it can betray the party; that behavior is a module too, switched on for the runs where I want to study it and off for the runs where I don't.

The obvious move is to write a prompt per configuration. It works, and it's wrong for the same reason writing a class per combination is wrong when you have behaviors and mixins. Fix something in the Hunter's tactical logic and you fix it in every file that contains a Hunter. Sharpen the speech module and you edit it everywhere it appears. The number of files grows as the product of the axes, and the number of places a single fix has to land grows with it.

But the constraint that actually settled it wasn't file count. **The configuration is chosen at runtime.** The speech style comes from a menu, mid-session. Whether betrayal is available depends on what I'm testing. I'm not shipping a directory of pre-rendered prompts for a choice the player makes in the moment.

So the modules stay separate — roles, speech, optional behaviors — and the prompt is compiled when the run starts, from whatever is selected. That's the whole idea.

## Where the idea came from

Not from prompt engineering. From Scala.

If you've written Scala, you know the stackable trait pattern: `class Hunter extends Agent with Terse with Profane`. You don't write a class per combination. You write the behaviors once and stack them.

The part everyone forgets is the part that actually matters — **linearization**. When two traits define the same thing, Scala doesn't shrug. There is a defined order of resolution, and that order is part of the language semantics. `with A with B` behaves differently from `with B with A`, and this is not a bug, it's the whole design.

Composition without a resolution rule is just concatenation. And concatenating prompt fragments is exactly what makes prompts unpredictable: two modules quietly disagree about tone, or format, or how much to explain, and the model picks a winner on its own, differently each run.

So the composer generates the resolution rules explicitly — two layers, both derived, neither hand-written into the prompt body.

**Identity supremacy** lands in a `<precedence>` block on every composition: identity governs; every other module (speech, traits, roles, imported skills) applies only insofar as consistent with `<identity>`; instructions that don't apply in the current context are ignored silently. That is the always-on rule, the floor under every stack.

**Trait conflicts** are separate. When two *active* traits declare each other as mutual conflicts, the composer emits a `<conflict_rule>` from their `priority` metadata — higher priority governs; equal priority is a build error, not a coin flip for the model. One-sided declarations don't invent a rule; they warn. No mutual pair, no `<conflict_rule>`.

Scala's linearization is the analogy for the second layer: a defined order when stacked behaviors collide. The first layer is stricter than Scala — identity always wins, regardless of what you `with`. Concatenation has neither.

```
<precedence>Identity governs. All other modules apply only insofar as
consistent with <identity>. Instructions inapplicable in the current
context are ignored silently.</precedence>
```

That's boring, explicit, and the difference between a method and a pile of text.

Worth saying plainly, because it's the first thing people assume: **this is not string concatenation.** Modules aren't glued end to end. They're parsed, typed, placed into declared slots, and the resolution rules between them are generated from what the modules themselves declare. Concatenation gives you a longer prompt. This gives you a prompt where you can say which part wins and why.

## What a module looks like

Markdown with frontmatter. The type is declared in the file, not in the filename — a module knows what it is regardless of where it sits.

Modules land in typed slots: `<identity>` is mandatory and governs; `<speech>` carries style; `<traits>` are discrete behavioral switches; `<output_rules>` is always emitted. The slot order is fixed and does not change between runs — which matters more than it sounds, and I'll come back to it.

Swapping the speech module changes the register and nothing else. Same Hunter, same tactical priorities, same output contract, different voice. That's the orthogonality you want: axes that move independently.

In the Streamlit playground it looks like this — same deep-research identity, same solar/inverter question, only the speech module changes:

![No speech module — formal clarifying questions](../assets/playground/01_no_speech_prompt.png)

*No speech — formal clarifying questions*

![ValeraPlumber speech — plumbing metaphors (pipes, Omsk)](../assets/playground/03_valera_omsk_pipes.png)

*Speech on — same task, different register*

The real payoff isn't the first composition — it's the second month. When I rewrote the speech module to calibrate intensity and add explicit boundaries, I touched one file. Every composition that includes it picked up the change on the next run. With monolithic prompts that's an edit in every file containing that voice, and the ones you forget drift quietly.

## Third-party modules stay third-party

Half the modules I use, I didn't write. There's a growing ecosystem of shared skill files, and reusing them is the point.

The naive approach is to copy the file and edit it into your library. Then upstream fixes something and you don't get it, because your copy forked the moment you touched it.

So vendored skills stay pristine under `vendor/`, and a thin overlay adapts them — declaring source, origin, and whether it's used as is or extracted. The upstream file is never edited. This is not a novel idea; it's how every package manager works. It just hadn't reached prompts.

## The part I didn't expect to need

Here's where it stopped being a convenience tool.

Once you can toggle modules, you start comparing. Does the terse trait actually improve the Guard's decisions, or does it just feel tighter? Does the speech module leak into tactical reasoning?

The first time I tried to answer that, I couldn't. I'd changed a module, rerun, and gotten a different result — but I no longer knew exactly what the previous prompt had been. Not approximately. Exactly. And in a system where a reordered sentence shifts behavior, approximately is useless.

So every compilation emits a manifest: module paths, content hashes, skeleton version, generated conflict rules. A receipt and a recipe. `compose_from_manifest` with hash verification rebuilds the exact prompt, or fails loudly if a module drifted underneath.

It's a lock file. `package-lock.json` for a persona.

This is also why the slot order is fixed rather than "whatever order you passed the modules in." Position affects attention. If the order shifts between runs, positional bias becomes a confounder and every comparison you make is measuring two things at once. Freeze it, and the only thing that varies is what you meant to vary.

## Ablation, because that's what the manifest is for

With composition and a manifest, one more thing becomes cheap: turn traits on and off systematically.

The composer builds the full 2^k grid over selected traits — baseline stays on in every cell, every cell gets its own manifest and prompt, and combinations that are invalid (two traits declared mutually exclusive at equal priority) get recorded as errors in the index instead of silently vanishing.

That's a factorial design. It isn't a new idea anywhere except here. Most prompt work is still: edit, rerun, squint, decide. If you have a way to build the grid and a way to prove which cell produced which output, you can do slightly better than squinting.

I want to be precise about what this gives you: a mechanism for generating and comparing configurations, and evidence of what was compared. It does not give you a score. You still need a metric and a judge, and that's a separate problem I'm not claiming to have solved. Generation is not learning until something tells you which output was better.

That said, this is where it gets interesting, and it's the direction I actually care about. If composing a skill is an action rather than a setup step, an agent's repertoire stops being fixed at design time. It can assemble a capability for a situation nobody anticipated, and if there's a signal telling it which assemblies worked, the selection can be learned rather than configured. That's the shape of skill discovery in RL, only the skills here are text artifacts instead of latent policies.

The compiler is the substrate for that, not the thing itself. Reward is somebody else's chapter — probably mine, later. But you can't learn over a space you have no way to generate, and generating that space reproducibly is the part that was missing.

## What it isn't

The core never calls a model. Composition is deterministic — same modules in, same prompt out, byte for byte. A model is only involved if you explicitly ask it to rewrite a module, and even then you inject the callable; the compiler doesn't reach out on its own.

That constraint is load-bearing. A compiler that phones home is a compiler you can't reason about.

One more thing falls out of having the composed prompt as an artifact you can inspect before it runs: you can check it. A basic compliance gate is implemented — deterministic regex rules in a Markdown file, run over the composed prompt or an exported skill, failing the build with the rule id that matched, and recording the ruleset hash in the manifest. It's aimed at third-party skill files carrying instructions your setup shouldn't be running.

It's early. The mechanism works and the default rule pack is deliberately small; what it needs is time against real skill files, and rules written by people who do this for a living rather than by me. But the shape seems right: the check runs on the artifact, before execution, with no model in the loop — so it holds regardless of what the model later decides to do with the text.

## Where it is

Python and TypeScript, same behavior, shared fixtures, golden XML tests. MIT.

The repo is [github.com/corba777/persona_composer](https://github.com/corba777/persona_composer).

The game is still the reason it exists. But the compiler turned out to be the part worth showing.
