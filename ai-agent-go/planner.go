package main

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

const planPromptTemplate = `You are a planning assistant for industrial asset operations and maintenance.

Decompose the question below into a sequence of subtasks. For each subtask,
assign a server and select the exact tool to call. Do NOT include tool arguments —
they will be resolved at execution time from the task description and prior results.

Available servers and tools:
{servers}

Output format — one block per step, exactly:

#Task1: <task description>
#Server1: <exact server name>
#Tool1: <exact tool name, or "none" if no tool call is needed>
#Dependency1: None
#ExpectedOutput1: <what this step should produce>

#Task2: <task description>
#Server2: <exact server name>
#Tool2: <exact tool name>
#Dependency2: #S1
#ExpectedOutput2: <what this step should produce>

Rules:
- Server and tool names must exactly match those listed above.
- Dependencies use #S<N> notation (e.g., #S1, #S2). Use "None" if none.
- Keep tasks specific and actionable.
- Prefer simple list/get tools over complex find/count query tools when the
  question only asks to list or inspect entities.
- Never invent entity names, IDs, timestamps, counts, or table rows in the
	plan itself.
- Use Tool="none" only when the step is a clarification or a non-factual
	coordination step; never use it to fabricate an answer.
- If the question asks for current ThingsBoard data, every data-bearing step
	must call a real tool and the final answer must be based only on tool output.
- Keep ExpectedOutput short and descriptive. It should describe the verified
	shape of the output, not contain the actual data.
- If a selected tool description says to call a guide tool first, add that
  guide tool as an earlier dependency step.

Question: {question}

Plan:
`

var (
	taskRE   = regexp.MustCompile(`#Task(\d+):\s*(.+)`)
	serverRE = regexp.MustCompile(`#Server(\d+):\s*(.+)`)
	toolRE   = regexp.MustCompile(`#Tool(\d+):\s*(.+)`)
	depRE    = regexp.MustCompile(`#Dependency(\d+):\s*(.+)`)
	outputRE = regexp.MustCompile(`#ExpectedOutput(\d+):\s*(.+)`)
	depNumRE = regexp.MustCompile(`#S(\d+)`)
)

func parsePlan(raw string) (Plan, error) {
	tasks := map[int]string{}
	servers := map[int]string{}
	tools := map[int]string{}
	depsRaw := map[int]string{}
	outputs := map[int]string{}

	for _, match := range taskRE.FindAllStringSubmatch(raw, -1) {
		n, _ := strconv.Atoi(match[1])
		tasks[n] = strings.TrimSpace(match[2])
	}
	for _, match := range serverRE.FindAllStringSubmatch(raw, -1) {
		n, _ := strconv.Atoi(match[1])
		servers[n] = strings.TrimSpace(match[2])
	}
	for _, match := range toolRE.FindAllStringSubmatch(raw, -1) {
		n, _ := strconv.Atoi(match[1])
		tools[n] = strings.TrimSpace(strings.Split(match[2], "(")[0])
	}
	for _, match := range depRE.FindAllStringSubmatch(raw, -1) {
		n, _ := strconv.Atoi(match[1])
		depsRaw[n] = strings.TrimSpace(match[2])
	}
	for _, match := range outputRE.FindAllStringSubmatch(raw, -1) {
		n, _ := strconv.Atoi(match[1])
		outputs[n] = strings.TrimSpace(match[2])
	}

	numbers := make([]int, 0, len(tasks))
	for number := range tasks {
		numbers = append(numbers, number)
	}
	sort.Ints(numbers)

	steps := make([]PlanStep, 0, len(numbers))
	for _, number := range numbers {
		rawDep := strings.TrimSpace(depsRaw[number])
		dependencies := []int{}
		if rawDep != "" && !strings.EqualFold(rawDep, "none") {
			matches := depNumRE.FindAllStringSubmatch(rawDep, -1)
			for _, match := range matches {
				dep, err := strconv.Atoi(match[1])
				if err != nil {
					return Plan{}, fmt.Errorf("invalid dependency format for step %d: %s", number, rawDep)
				}
				if dep < 1 || dep >= number {
					return Plan{}, fmt.Errorf("invalid dependency reference for step %d: #S%d", number, dep)
				}
				dependencies = append(dependencies, dep)
			}
			if len(dependencies) == 0 {
				return Plan{}, fmt.Errorf("invalid dependency format for step %d: %s", number, rawDep)
			}
		}

		steps = append(steps, PlanStep{
			StepNumber:     number,
			Task:           tasks[number],
			Server:         servers[number],
			Tool:           tools[number],
			ToolArgs:       map[string]any{},
			Dependencies:   dependencies,
			ExpectedOutput: outputs[number],
		})
	}

	return Plan{Steps: steps, Raw: raw}, nil
}

type Planner struct {
	llm *OllamaClient
}

func (p *Planner) GeneratePlan(question string, serverDescriptions map[string]string) (Plan, error) {
	serverNames := make([]string, 0, len(serverDescriptions))
	for name := range serverDescriptions {
		serverNames = append(serverNames, name)
	}
	sort.Strings(serverNames)
	blocks := make([]string, 0, len(serverNames))
	for _, name := range serverNames {
		blocks = append(blocks, fmt.Sprintf("%s:\n%s", name, serverDescriptions[name]))
	}
	prompt := strings.NewReplacer(
		"{servers}", strings.Join(blocks, "\n\n"),
		"{question}", question,
	).Replace(planPromptTemplate)
	raw, err := p.llm.Generate(prompt)
	if err != nil {
		return Plan{}, err
	}
	return parsePlan(raw)
}
