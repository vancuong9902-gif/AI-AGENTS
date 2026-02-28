from app.db.base_class import Base

# Import tất cả models để Base.metadata có đủ table
from app.models.user import User
from app.models.session import Session
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_topic import DocumentTopic
from app.models.rag_query import RAGQuery
from app.models.learner_profile import LearnerProfile
from app.models.quiz_set import QuizSet
from app.models.question import Question
from app.models.attempt import Attempt

from app.models.diagnostic_attempt import DiagnosticAttempt

from app.models.learning_plan import LearningPlan, LearningPlanTaskCompletion, LearningPlanHomeworkSubmission
from app.models.classroom import Classroom, ClassroomMember
from app.models.classroom_assessment import ClassroomAssessment

from app.models.student_assignment import StudentAssignment
from app.models.class_report import ClassReport
