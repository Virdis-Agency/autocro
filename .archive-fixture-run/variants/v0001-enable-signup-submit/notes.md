# Notes for v0001-enable-signup-submit

- Iteration: 1
- Research direction: explore
- Target page: `/signup`
- Rejected sub-variants considered this iteration:
  - "Trim signup form fields from 11 to 4 (email + password + name + company)" — defensible from form_friction data but does not address the *primary* observed blocker (the disabled button); deferred for a later iteration once the unblock-and-measure baseline exists.
  - "Replace 'Learn more' CTAs on `/` and `/pricing` with task-specific verbs ('Start free trial')" — strong theoretical lift, but funnel data shows the bottleneck is `submit`, not the upstream CTAs; not the highest-priority change while the goal event is mechanically broken.
  - "Add quantified social proof to hero" — speculative, no specific data citation in the heatmap/funnel for trust as the bottleneck.

## simplicity-review
decision: ok
reason: 2 diff lines, single attribute removal on primary submit; no debug/dead-code/over-cleverness
