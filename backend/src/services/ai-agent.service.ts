import Anthropic from '@anthropic-ai/sdk';

type RoleMessage = { role: string; content: string };

export class AIAgentService {
  private client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  private model = 'claude-sonnet-4-20250514';

  private async callJSON(system: string, userContent: string, retries = 3): Promise<any> {
    for (let i = 0; i < retries; i += 1) {
      try {
        const response = await this.client.messages.create({
          model: this.model,
          max_tokens: 8192,
          system: `${system}\nEnsure all Vietnamese text uses proper Unicode (UTF-8) characters. Return ONLY valid JSON. No markdown. No code fences. No explanation.`,
          messages: [{ role: 'user', content: userContent }]
        });
        const text = response.content[0].type === 'text' ? response.content[0].text : '{}';
        return JSON.parse(text);
      } catch (error) {
        if (i === retries - 1) throw error;
        await new Promise((resolve) => setTimeout(resolve, 2 ** i * 1000));
      }
    }
  }

  async processPDF(pdfText: string, subject: string) { return this.callJSON('Bạn là chuyên gia thiết kế chương trình học.', `Môn học: ${subject}\n${pdfText}`); }
  async generateEntryTestQuestions(topics: any[], config: any) { return this.callJSON('Sinh câu hỏi đầu vào', JSON.stringify({ topics, config })); }
  async generateFinalExamQuestions(topics: any[], config: any, studentLevel: string) { return this.callJSON('Sinh câu hỏi cuối kỳ', JSON.stringify({ topics, config, studentLevel })); }
  async gradeExercise(prompt: string, sampleAnswer: string, studentAnswer: string) { return this.callJSON('Chấm bài tập', JSON.stringify({ prompt, sampleAnswer, studentAnswer })); }
  async tutorChat(message: string, topicTitles: string[], subject: string, history: RoleMessage[]) {
    const result = await this.callJSON('Gia sư AI theo phạm vi chủ đề', JSON.stringify({ message, topicTitles, subject, history: history.slice(-10) }));
    return result.reply;
  }
  async generateStudentAssessment(data: Record<string, unknown>) { const r = await this.callJSON('Đánh giá học sinh', JSON.stringify(data)); return r.assessment; }
  async generateExamVersions(topics: any[], config: any) { return this.callJSON('Sinh nhiều mã đề', JSON.stringify({ topics, config })); }
}

export const aiAgentService = new AIAgentService();
