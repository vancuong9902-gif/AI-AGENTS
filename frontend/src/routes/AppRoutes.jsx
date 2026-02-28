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
import TeacherCreateEntryTest from "../pages/TeacherCreateEntryTest";
import StudentClassrooms from "../pages/StudentClassrooms";
import StudentDashboard from "../pages/StudentDashboard";
import AgentFlow from "../pages/AgentFlow";

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
        path="/result"
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
        path="/teacher/files"
        element={
          <ProtectedRoute allow={["teacher"]}>
            <FileLibrary />
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
    </Routes>
  );
}
