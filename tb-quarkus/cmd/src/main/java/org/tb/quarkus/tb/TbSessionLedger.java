package org.tb.quarkus.tb;

import io.quarkus.logging.Log;
import jakarta.enterprise.context.ApplicationScoped;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * A per-run undo log. Every mutating TbGateway call that creates or changes
 * something registers a matching {@link Step} here; if the run fails partway
 * through, {@link #rollbackAll()} unwinds everything in reverse order.
 *
 * Deliberately NOT transactional in the database sense - ThingsBoard has no
 * multi-entity transaction API over REST, so this is best-effort compensation:
 * each step's undo action is executed independently, and one failing undo
 * doesn't stop the rest from being attempted (you want maximum cleanup, not
 * an early bailout that leaves half the mess behind).
 */
@ApplicationScoped
public class TbSessionLedger {

    /** One undoable action: what it was, and how to reverse it. */
    public record Step(String description, ThrowingRunnable undo) {
    }

    @FunctionalInterface
    public interface ThrowingRunnable {
        void run() throws Exception;
    }

    private final Deque<Step> steps = new ArrayDeque<>();

    /** Call at the start of each run - a ledger instance shouldn't carry over between invocations. */
    public void reset() {
        steps.clear();
    }

    public void record(String description, ThrowingRunnable undo) {
        steps.addLast(new Step(description, undo));
    }

    public int size() {
        return steps.size();
    }

    /**
     * Undoes every recorded step, most-recent-first. Logs and continues past
     * individual undo failures instead of aborting the rollback.
     *
     * @return number of steps that failed to undo
     */
    public int rollbackAll() {
        int failures = 0;
        Log.warnf("Rolling back %d ThingsBoard change(s) from this run...", steps.size());
        while (!steps.isEmpty()) {
            Step step = steps.pollLast(); // most recent first
            try {
                step.undo().run();
                Log.infof("  rolled back: %s", step.description());
            } catch (Exception e) {
                failures++;
                Log.errorf("  FAILED to roll back '%s': %s", step.description(), e.getMessage());
            }
        }
        if (failures > 0) {
            Log.warnf("Rollback finished with %d step(s) that could not be undone - check ThingsBoard manually.", failures);
        } else {
            Log.info("Rollback complete - ThingsBoard state restored.");
        }
        return failures;
    }
}
