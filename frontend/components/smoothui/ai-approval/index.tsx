"use client";

/*
 * SmoothUI AI Approval
 * Source: https://smoothui.dev/docs/components/ai-approval
 * Copyright (c) 2024 Eduardo Calvo — MIT; see ../LICENSE.
 * Adapted with disabled/pending states so server-backed decisions stay truthful.
 */

import { cn } from "@/lib/utils";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { type ReactNode, useState } from "react";

const SPRING_DEFAULT = {
  bounce: 0.1,
  duration: 0.25,
  type: "spring" as const,
};
const EASE_OUT = [0.23, 1, 0.32, 1] as const;
const CHOICE_STAGGER = 0.03;

export type AIApprovalOption = {
  /** Marks the option as the destructive one, e.g. "Delete everything". */
  destructive?: boolean;
  /** Secondary line under the label. */
  detail?: string;
  id: string;
  label: string;
};

export type AIApprovalProps = {
  className?: string;
  /** Extra context under the question. */
  children?: ReactNode;
  /** Prevent decisions until surrounding validation is complete. */
  disabled?: boolean;
  /** Called once, with the chosen option. */
  onDecide?: (option: AIApprovalOption) => void;
  options: AIApprovalOption[];
  /** Marks the chosen decision as awaiting server confirmation. */
  pending?: boolean;
  /** What the agent needs a human to settle. */
  question: string;
  /** Render already-resolved, e.g. when replaying a transcript. */
  resolvedId?: string;
};

/**
 * The card an agent puts up before it acts.
 *
 * Choosing does not tick a radio button — the chosen option expands to fill the
 * card and the alternatives collapse out of existence. The decision should look
 * as irreversible as it is; leaving the rejected options sitting there greyed out
 * invites a second look at something that already happened.
 */
const AIApproval = ({
  className,
  children,
  disabled = false,
  onDecide,
  options,
  pending = false,
  question,
  resolvedId,
}: AIApprovalProps) => {
  const shouldReduceMotion = useReducedMotion();
  const [chosenId, setChosenId] = useState<string | null>(resolvedId ?? null);

  const chosen = options.find((option) => option.id === chosenId) ?? null;

  const decide = (option: AIApprovalOption) => {
    if (chosenId || disabled || pending) {
      return;
    }
    setChosenId(option.id);
    onDecide?.(option);
  };

  return (
    <motion.div
      aria-busy={pending}
      className={cn(
        "w-full rounded-xl border border-border bg-background p-3.5",
        className
      )}
      layout={!shouldReduceMotion}
      transition={shouldReduceMotion ? { duration: 0 } : SPRING_DEFAULT}
    >
      <motion.div layout={!shouldReduceMotion}>
        <p className="font-medium text-foreground text-sm">{question}</p>
        {children ? (
          <div className="mt-1 text-muted-foreground text-xs leading-relaxed">
            {children}
          </div>
        ) : null}
      </motion.div>

      <div className="mt-3">
        <AnimatePresence initial={false} mode="popLayout">
          {chosen ? (
            <motion.div
              animate={{ opacity: 1, scale: 1 }}
              className={cn(
                "flex items-center gap-2 rounded-lg px-3 py-2 text-sm",
                chosen.destructive
                  ? "bg-destructive/10 text-destructive"
                  : "bg-foreground text-background"
              )}
              initial={
                shouldReduceMotion
                  ? { opacity: 1, scale: 1 }
                  : { opacity: 0, scale: 0.97 }
              }
              key="resolved"
              role="status"
              transition={shouldReduceMotion ? { duration: 0 } : SPRING_DEFAULT}
            >
              <span className="flex size-4 items-center justify-center">
                <svg aria-hidden="true" viewBox="0 0 14 14" className="size-3.5 fill-none stroke-current">
                  <path d="m2.5 7.5 3 3 6-7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                </svg>
              </span>
              <span className="font-medium">{chosen.label}</span>
              {chosen.detail ? (
                <span className="ml-auto text-xs opacity-70">
                  {pending ? "正在提交…" : chosen.detail}
                </span>
              ) : null}
            </motion.div>
          ) : (
            <motion.div
              className="flex flex-col gap-1.5"
              exit={
                shouldReduceMotion
                  ? { opacity: 0, transition: { duration: 0 } }
                  : { opacity: 0, scale: 0.98 }
              }
              key="options"
              transition={
                shouldReduceMotion
                  ? { duration: 0 }
                  : { duration: 0.16, ease: EASE_OUT }
              }
            >
              {options.map((option, index) => (
                <motion.button
                  animate={{ opacity: 1, y: 0 }}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                    option.destructive
                      ? "border-destructive/30 text-destructive hover:bg-destructive/10"
                      : "border-border text-foreground hover:bg-muted"
                  )}
                  disabled={disabled || pending}
                  initial={
                    shouldReduceMotion
                      ? { opacity: 1, y: 0 }
                      : { opacity: 0, y: 4 }
                  }
                  key={option.id}
                  onClick={() => decide(option)}
                  transition={
                    shouldReduceMotion
                      ? { duration: 0 }
                      : { ...SPRING_DEFAULT, delay: index * CHOICE_STAGGER }
                  }
                  type="button"
                  whileTap={shouldReduceMotion || disabled ? undefined : { scale: 0.99 }}
                >
                  <span className="font-medium">{option.label}</span>
                  {option.detail ? (
                    <span className="ml-auto text-muted-foreground text-xs">
                      {option.detail}
                    </span>
                  ) : null}
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};

export default AIApproval;
