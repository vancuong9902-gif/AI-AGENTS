import { Routes, Route } from "react-router-dom";
import Login from "../pages/Login";
import Upload from "../pages/Upload";
import Health from "../pages/Health";
import Quiz from "../pages/Quiz";
import Result from "../pages/Result";
import LearningPath from "../pages/LearningPath";
import Tutor from "../pages/Tutor";
import Progress from "../pages/Progress";
import ProtectedRoute from "./ProtectedRoute";
import FileLibrary from "../pages/FileLibrary";

import Assessments from "../pages/Assessments";
import AssessmentTake from "../pages/AssessmentTake";

import TeacherAssessments from "../pages/TeacherAssessments";
import TeacherLeaderboard from "../pages/TeacherLeaderboard";
import TeacherGrade from "../pages/TeacherGrade";
import TeacherStudentPlan from "../pages/TeacherStudentPlan";
import TeacherAnalyticsDashboard from "../pages/TeacherAnalyticsDashboard";
import TeacherInfraDashboard from "../pages/TeacherInfraDashboard";
import StudentAnalyticsDashboard from "../pages/StudentAnalyticsDashboard";

import TeacherClassrooms from "../pages/TeacherClassrooms";
import TeacherClassroomDashboard from "../pages/TeacherClassroomDashboard";
import TeacherClassReportDetail from "../pages/TeacherClassReportDetail";
import TeacherCreateEntryTest from "../pages/TeacherCreateEntryTest";
import TeacherStudentReport from "../pages/TeacherStudentReport";
import TeacherTopicReview from "../pages/TeacherTopicReview";
import StudentClassrooms from "../pages/StudentClassrooms";
import StudentDashboard from "../pages/StudentDashboard";
import AgentFlow from "../pages/AgentFlow";
import TopicDetail from "../pages/TopicDetail";
import StudentPractice from "../pages/StudentPractice";
import FinalExam from "../pages/FinalExam";
import TopicPreview from "../pages/TopicPreview";
import TopicSelection from "../pages/TopicSelection";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />

      <Route
        path="/upload"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <Upload />
          </ProtectedRoute>
        }
      />

      <Route
        path="/documents/:docId/topics/preview"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TopicPreview />
          </ProtectedRoute>
        }
      />

      <Route path="/health" element={<Health />} />

      <Route
        path="/quiz"
        element={
          <ProtectedRoute allow={["student"]}>
            <Quiz />
          </ProtectedRoute>
        }
      />

      <Route
        path="/learning-path"
        element={
          <ProtectedRoute allow={["student"]}>
            <LearningPath />
          </ProtectedRoute>
        }
      />

      <Route
        path="/topic/:documentId/:topicId"
        element={
          <ProtectedRoute allow={["student"]}>
            <TopicDetail />
          </ProtectedRoute>
        }
      />

      <Route
        path="/practice"
        element={
          <ProtectedRoute allow={["student"]}>
            <StudentPractice />
          </ProtectedRoute>
        }
      />

      <Route
        path="/quiz/:topicId"
        element={
          <ProtectedRoute allow={["student"]}>
            <Quiz />
          </ProtectedRoute>
        }
      />


      <Route
        path="/tutor"
        element={
          <ProtectedRoute allow={["student"]}>
            <Tutor />
          </ProtectedRoute>
        }
      />

      <Route
        path="/analytics"
        element={
          <ProtectedRoute allow={["student"]}>
            <StudentAnalyticsDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/progress"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <Progress />
          </ProtectedRoute>
        }
      />

      <Route
        path="/result/:attemptId"
        element={
          <ProtectedRoute allow={["student"]}>
            <Result />
          </ProtectedRoute>
        }
      />

      <Route
        path="/assessments"
        element={
          <ProtectedRoute allow={["student"]}>
            <Assessments />
          </ProtectedRoute>
        }
      />

      <Route
        path="/assessments/:id"
        element={
          <ProtectedRoute allow={["student"]}>
            <AssessmentTake />
          </ProtectedRoute>
        }
      />

      <Route
        path="/final-exam"
        element={
          <ProtectedRoute allow={["student"]}>
            <FinalExam />
          </ProtectedRoute>
        }
      />

      <Route
        path="/final-exam/:classroomId"
        element={
          <ProtectedRoute allow={["student"]}>
            <FinalExam />
          </ProtectedRoute>
        }
      />

      <Route
        path="/classrooms"
        element={
          <ProtectedRoute allow={["student"]}>
            <StudentClassrooms />
          </ProtectedRoute>
        }
      />

      <Route
        path="/student-dashboard"
        element={
          <ProtectedRoute allow={["student"]}>
            <StudentDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/agent-flow"
        element={
          <ProtectedRoute allow={["student"]}>
            <AgentFlow />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/infra"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherInfraDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/assessments"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherAssessments />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/classrooms"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherClassrooms />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/classrooms/:id"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherClassroomDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/classrooms/:id/reports/:reportId"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherClassReportDetail />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/classrooms/:id/entry-test"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherCreateEntryTest />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/assessments/:id/leaderboard"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherLeaderboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/assessments/:id/grade/:studentId"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherGrade />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/progress/:studentId?"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <Progress />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/analytics/:studentId?"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherAnalyticsDashboard />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/student-plan/:studentId"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherStudentPlan />
          </ProtectedRoute>
        }
      />


      <Route
        path="/teacher/classrooms/:classroomId/documents/:documentId/topics"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TopicSelection />
          </ProtectedRoute>
        }
      />

      <Route
        path="/teacher/files"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <FileLibrary />
          </ProtectedRoute>
        }
      />


      <Route
        path="/teacher/documents/:docId/topic-review"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherTopicReview />
          </ProtectedRoute>
        }
      />

      <Route
        path="/files"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <FileLibrary />
          </ProtectedRoute>
        }
      />
    

      <Route
        path="/teacher/reports/student/:studentId"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <TeacherStudentReport />
          </ProtectedRoute>
        }
      />
</Routes>
  );
}
