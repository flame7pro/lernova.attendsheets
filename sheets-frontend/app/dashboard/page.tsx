'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context-email';
import { classService, Class } from '@/lib/classService';
import { Menu, User, Users, LayoutDashboard } from 'lucide-react';

import { Sidebar } from '../components/dashboard/Sidebar';
import { EmptyState } from '../components/dashboard/EmptyState';
import { AttendanceSheet } from '../components/dashboard/AttendanceSheet';
import { AllClassesView } from '../components/dashboard/AllClassesView';
import { SnapshotView } from '../components/dashboard/SnapshotView';
import { ClassThresholdSettings } from '../components/dashboard/ClassThresholdSettings';
import { SettingsModal } from '../components/dashboard/SettingsModal';
import { ChangePasswordModal } from '../components/dashboard/ChangePasswordModal';
import { AddClassModal } from '../components/dashboard/AddClassModal';
import { AddColumnModal } from '../components/dashboard/AddColumnModal';
import { DeleteClassModal } from '../components/dashboard/DeleteClassModal';
import { ImportDataState } from '../components/dashboard/ImportDataState';
import { MonthYearSelector } from '../components/dashboard/MonthYearSelector';
import { AttendanceThresholds, Student, CustomColumn } from '@/types';
import { QRAttendanceModal } from '../components/QRAttendanceModal';

export default function DashboardPage() {
  const router = useRouter();
  const { user, logout, isAuthenticated, loading } = useAuth();

  const sanitizeAttendance = (attendance: Record<string, any>): Record<string, any> => {
    const sanitized: Record<string, any> = {};
    for (const [key, value] of Object.entries(attendance)) {
      if (value !== undefined && value !== null) {
        sanitized[key] = value;
      }
    }
    return sanitized;
  };

  const sanitizeClass = (cls: any): Class => ({
    ...cls,
    id: String(cls.id), // ✅ ensure string id
    students: (cls.students || []).map((student: any) => ({
      ...student,
      attendance: sanitizeAttendance(student.attendance || {}),
    })),
    customColumns: cls.customColumns || [],
    thresholds: cls.thresholds || defaultThresholds,
  });

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [classes, setClasses] = useState<Class[]>([]);
  const [activeClassId, setActiveClassId] = useState<string | null>(null);
  const [showAllClasses, setShowAllClasses] = useState(false);
  const [showSnapshot, setShowSnapshot] = useState(true);
  const [showImportState, setShowImportState] = useState(false);
  const [pendingClassName, setPendingClassName] = useState('');
  const [currentMonth, setCurrentMonth] = useState(new Date().getMonth());
  const [currentYear, setCurrentYear] = useState(new Date().getFullYear());
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState('');
  const [showQRModal, setShowQRModal] = useState(false);

  const [defaultThresholds, setDefaultThresholds] = useState<AttendanceThresholds>({
    excellent: 95,
    good: 90,
    moderate: 85,
    atRisk: 85,
  });

  const [showAddClassModal, setShowAddClassModal] = useState(false);
  const [showAddColumnModal, setShowAddColumnModal] = useState(false);
  const [showDeleteClassModal, setShowDeleteClassModal] = useState(false);
  const [showThresholdSettings, setShowThresholdSettings] = useState(false);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [showChangePasswordModal, setShowChangePasswordModal] = useState(false);
  const [settingsClassId, setSettingsClassId] = useState<string | null>(null);
  const [classToDelete, setClassToDelete] = useState<Class | null>(null);
  const [newClassName, setNewClassName] = useState('');
  const [newColumnLabel, setNewColumnLabel] = useState('');
  const [newColumnType, setNewColumnType] = useState<'text' | 'number' | 'select'>('text');

  // Redirect if not authenticated
  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push('/auth');
    }
  }, [isAuthenticated, loading, router]);

  // Prevent back navigation
  useEffect(() => {
    if (isAuthenticated && typeof window !== 'undefined') {
      window.history.pushState(null, '', window.location.href);
      const handlePopState = () => {
        window.history.pushState(null, '', window.location.href);
      };
      window.addEventListener('popstate', handlePopState);
      return () => {
        window.removeEventListener('popstate', handlePopState);
      };
    }
  }, [isAuthenticated]);

  // Load classes from backend on mount
  useEffect(() => {
    if (user && isAuthenticated) {
      loadClassesFromBackend();
    }
  }, [user, isAuthenticated]);

  // Load thresholds from localStorage
  useEffect(() => {
    if (user) {
      const savedThresholds = localStorage.getItem(`default_thresholds_${user.id}`);
      if (savedThresholds) {
        setDefaultThresholds(JSON.parse(savedThresholds));
      }
    }
  }, [user]);

  // Save thresholds to localStorage
  useEffect(() => {
    if (user) {
      localStorage.setItem(`default_thresholds_${user.id}`, JSON.stringify(defaultThresholds));
    }
  }, [defaultThresholds, user]);

  // Load classes from backend
  const loadClassesFromBackend = async () => {
    try {
      setSyncing(true);
      setSyncError('');
      const backendClasses = await classService.loadClasses();
      if (backendClasses.length > 0) {
        const sanitized = backendClasses.map(sanitizeClass);
        setClasses(sanitized);
        setShowSnapshot(true);
        setActiveClassId(sanitized[0].id);
      } else {
        // Try loading from localStorage as fallback
        const localClasses = localStorage.getItem(`classes_${user?.id}`);
        if (localClasses) {
          const parsed: Class[] = JSON.parse(localClasses);
          const sanitized = parsed.map(sanitizeClass);
          setClasses(sanitized);
          if (sanitized.length > 0) {
            setActiveClassId(sanitized[0].id);
          }
          // Sync local classes to backend
          if (parsed.length > 0) {
            await syncToBackend(sanitized);
          }
        }
      }
    } catch (error) {
      console.error('Error loading classes:', error);
      setSyncError('Failed to sync with server. Working offline.');
      // Load from localStorage as fallback
      const localClasses = localStorage.getItem(`classes_${user?.id}`);
      if (localClasses) {
        const parsed: Class[] = JSON.parse(localClasses);
        const sanitized = parsed.map(sanitizeClass);
        setClasses(sanitized);
        if (sanitized.length > 0) {
          setActiveClassId(sanitized[0].id);
        }
      }
    } finally {
      setSyncing(false);
    }
  };

  // Sync classes to backend
  const syncToBackend = async (classesToSync: Class[]) => {
    if (!user) return;
    try {
      await classService.syncClasses(classesToSync);
      console.log('Classes synced successfully');
    } catch (error) {
      console.error('Error syncing classes:', error);
      setSyncError('Failed to sync some changes');
    }
  };

  // Save class to backend and localStorage
  const saveClass = async (updatedClass: Class) => {
    const sanitizedClass = sanitizeClass(updatedClass);
    const updatedClasses = classes.map(c => (c.id === sanitizedClass.id ? sanitizedClass : sanitizeClass(c)));
    setClasses(updatedClasses);

    // Save to localStorage immediately
    if (user) {
      localStorage.setItem(`classes_${user.id}`, JSON.stringify(updatedClasses));
    }

    // Sync to backend asynchronously (don't block UI)
    try {
      await classService.updateClass(String(sanitizedClass.id), sanitizedClass);
      setSyncError('');
    } catch (error) {
      console.error('Error saving class to backend:', error);
      // data is saved locally; backend will sync when connection is restored
    }
  };

  const handleLogout = async () => {
    await logout();
    router.push('/auth');
  };

  const handleOpenSettings = () => {
    setShowSettingsModal(true);
  };

  const handlePasswordChangeClick = () => {
    setShowChangePasswordModal(true);
  };

  const handleSaveThresholds = (newThresholds: AttendanceThresholds, applyToClassIds: string[]) => {
    const updatedClasses = classes.map(cls =>
      applyToClassIds.includes(cls.id) ? { ...cls, thresholds: newThresholds } : cls
    );
    const sanitized = updatedClasses.map(sanitizeClass);
    setClasses(sanitized);

    // Sync each updated class
    sanitized.forEach(cls => {
      if (applyToClassIds.includes(cls.id)) {
        saveClass(cls);
      }
    });
  };

  const handleOpenClassSettings = (classId: string) => {
    setSettingsClassId(classId);
    setShowThresholdSettings(true);
  };

  const handleAddClass = () => {
    if (!newClassName.trim()) return;
    setPendingClassName(newClassName);
    setNewClassName('');
    setShowAddClassModal(false);
    setShowImportState(true);
  };

  const handleManualInput = async () => {
    const newId = Date.now().toString(); // ✅ string id
    const newClass: Class = {
      id: newId,
      name: pendingClassName,
      students: [],
      customColumns: [],
      thresholds: undefined,
    };

    const updatedClasses = [...classes, newClass].map(sanitizeClass);
    setClasses(updatedClasses);
    setActiveClassId(newId);
    setShowImportState(false);
    setShowSnapshot(false);
    setPendingClassName('');

    // Save to backend
    try {
      await classService.createClass(newClass);
      setSyncError('');
    } catch (error) {
      console.error('Error creating class:', error);
      setSyncError('Failed to sync new class');
    }
  };

  const handleImportComplete = async (data: any) => {
    const newId = Date.now().toString(); // ✅ string id
    const newClass: Class = {
      id: newId,
      name: pendingClassName,
      students: data.students || [],
      customColumns: data.customColumns || [],
      thresholds: undefined,
    };

    const updatedClasses = [...classes, newClass].map(sanitizeClass);
    setClasses(updatedClasses);
    setActiveClassId(newId);
    setShowImportState(false);
    setShowSnapshot(false);
    setPendingClassName('');

    // Save to backend
    try {
      await classService.createClass(newClass);
      setSyncError('');
    } catch (error) {
      console.error('Error creating class:', error);
      setSyncError('Failed to sync new class');
    }
  };

  const handleCancelImport = () => {
    setShowImportState(false);
    setPendingClassName('');
  };

  const handleDeleteClass = (classId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const cls = classes.find(c => c.id === classId);
    if (cls) {
      setClassToDelete(cls);
      setShowDeleteClassModal(true);
    }
  };

  const confirmDeleteClass = async () => {
    if (!classToDelete) return;

    const updatedClasses = classes.filter(c => c.id !== classToDelete.id);
    const sanitized = updatedClasses.map(sanitizeClass);
    setClasses(sanitized);

    // Update localStorage immediately
    if (user) {
      localStorage.setItem(`classes_${user.id}`, JSON.stringify(sanitized));
    }

    if (activeClassId === classToDelete.id) {
      if (sanitized.length > 0) {
        setShowSnapshot(true);
        setActiveClassId(null);
      } else {
        setActiveClassId(null);
        setShowSnapshot(false);
      }
    }

    // Delete from backend
    try {
      await classService.deleteClass(String(classToDelete.id));
      setSyncError('');
    } catch (error) {
      console.error('Error deleting class:', error);
      setSyncError('Failed to sync deletion');
    }

    setShowDeleteClassModal(false);
    setClassToDelete(null);
  };

  const handleClassSelect = (id: string) => {
    setActiveClassId(id);
    setShowAllClasses(false);
    setShowSnapshot(false);
  };

  const handleUpdateClassName = (classId: string, newName: string) => {
    const updatedClasses = classes.map(cls =>
      cls.id === classId ? { ...cls, name: newName } : cls
    );
    const sanitizedClasses = updatedClasses.map(sanitizeClass);
    setClasses(sanitizedClasses);

    const updatedClass = sanitizedClasses.find(c => c.id === classId);
    if (updatedClass) {
      saveClass(updatedClass);
    }
  };

  const handleAddStudent = () => {
    if (!activeClassId) return;

    const newStudent: Student = {
      id: Date.now(),
      rollNo: '',
      name: '',
      attendance: {},
    };

    const updatedClasses = classes.map(cls =>
      cls.id === activeClassId
        ? { ...cls, students: [...cls.students, newStudent] }
        : cls
    );

    const sanitizedClasses = updatedClasses.map(sanitizeClass);
    setClasses(sanitizedClasses);

    const updatedClass = sanitizedClasses.find(c => c.id === activeClassId);
    if (updatedClass) {
      saveClass(updatedClass);
    }
  };

  const handleUpdateStudent = (studentId: number, field: string, value: any) => {
    if (!activeClassId) return;

    const updatedClasses = classes.map(cls =>
      cls.id === activeClassId
        ? {
            ...cls,
            students: cls.students.map(student =>
              student.id === studentId ? { ...student, [field]: value } : student
            ),
          }
        : cls
    );

    const sanitizedClasses = updatedClasses.map(sanitizeClass);
    setClasses(sanitizedClasses);

    const updatedClass = sanitizedClasses.find(c => c.id === activeClassId);
    if (updatedClass) {
      saveClass(updatedClass);
    }
  };

  const handleDeleteStudent = (studentId: number) => {
    if (!activeClassId) return;

    const updatedClasses = classes.map(cls =>
      cls.id === activeClassId
        ? {
            ...cls,
            students: cls.students.filter(s => s.id !== studentId),
          }
        : cls
    );

    const sanitizedClasses = updatedClasses.map(sanitizeClass);
    setClasses(sanitizedClasses);

    const updatedClass = sanitizedClasses.find(c => c.id === activeClassId);
    if (updatedClass) {
      saveClass(updatedClass);
    }
  };

  const handleToggleAttendance = (studentId: number, day: number) => {
    if (!activeClassId) return;

    const dateKey = `${currentYear}-${currentMonth + 1}-${day}`;

    const updatedClasses = classes.map(cls =>
      cls.id === activeClassId
        ? {
            ...cls,
            students: cls.students.map(student => {
              if (student.id === studentId) {
                const currentStatus = (student as any).attendance[dateKey];
                let newStatus: 'P' | 'A' | 'L' | undefined;

                if (!currentStatus) {
                  newStatus = 'P';
                } else if (currentStatus === 'P') {
                  newStatus = 'A';
                } else if (currentStatus === 'A') {
                  newStatus = 'L';
                } else {
                  newStatus = undefined;
                }

                return {
                  ...student,
                  attendance: {
                    ...(student as any).attendance,
                    [dateKey]: newStatus,
                  },
                };
              }
              return student;
            }),
          }
        : cls
    );

    const sanitizedClasses = updatedClasses.map(sanitizeClass);
    setClasses(sanitizedClasses);

    const updatedClass = sanitizedClasses.find(c => c.id === activeClassId);
    if (updatedClass) {
      saveClass(updatedClass);
    }
  };

  const handleAddColumn = () => {
    if (!newColumnLabel.trim() || !activeClassId) return;

    const newColumn: CustomColumn = {
      id: `col_${Date.now()}`,
      label: newColumnLabel,
      type: newColumnType,
    };

    const updatedClasses = classes.map(cls =>
      cls.id === activeClassId
        ? { ...cls, customColumns: [...cls.customColumns, newColumn] }
        : cls
    );

    const sanitizedClasses = updatedClasses.map(sanitizeClass);
    setClasses(sanitizedClasses);

    setNewColumnLabel('');
    setNewColumnType('text');
    setShowAddColumnModal(false);

    const updatedClass = sanitizedClasses.find(c => c.id === activeClassId);
    if (updatedClass) {
      saveClass(updatedClass);
    }
  };

  const handleDeleteColumn = (columnId: string) => {
    if (!activeClassId) return;

    const updatedClasses = classes.map(cls =>
      cls.id === activeClassId
        ? {
            ...cls,
            customColumns: cls.customColumns.filter(col => col.id !== columnId),
            students: cls.students.map(student => {
              const { [columnId]: _, ...rest } = student as any;
              return rest as Student;
            }),
          }
        : cls
    );

    const sanitizedClasses = updatedClasses.map(sanitizeClass);
    setClasses(sanitizedClasses);

    const updatedClass = sanitizedClasses.find(c => c.id === activeClassId);
    if (updatedClass) {
      saveClass(updatedClass);
    }
  };

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!isAuthenticated) {
    return null;
  }

  const activeClass = classes.find(c => c.id === activeClassId) || null;

  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Sidebar */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed(!sidebarCollapsed)}
        classes={classes}
        activeClassId={activeClassId}
        onAddClass={() => setShowAddClassModal(true)}
        onClassSelect={handleClassSelect}
        onDeleteClass={handleDeleteClass}
        onViewAllClasses={() => {
          setShowAllClasses(true);
          setShowSnapshot(false);
          setShowImportState(false);
        }}
        onViewSnapshot={() => {
          setShowSnapshot(true);
          setShowAllClasses(false);
          setShowImportState(false);
          setActiveClassId(null);
        }}
        onOpenSettings={handleOpenSettings}
        onLogout={handleLogout}
        onUpdateClassName={handleUpdateClassName}
        syncing={syncing}
        syncError={syncError}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-200">
          <div className="flex items-center gap-3">
            <button
              className="md:hidden p-2 rounded-lg hover:bg-slate-100"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            >
              <Menu className="w-5 h-5 text-slate-700" />
            </button>
            <div>
              <h1 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
                <LayoutDashboard className="w-5 h-5 text-emerald-600" />
                Dashboard
              </h1>
              <p className="text-sm text-slate-500">
                Manage your classes, students, and attendance.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <MonthYearSelector
              currentMonth={currentMonth}
              currentYear={currentYear}
              onMonthChange={(month: number) => {
                setCurrentMonth(month);
              }}
              onYearChange={(year: number) => {
                setCurrentYear(year);
              }}
            />
            <div className="flex items-center gap-2 px-3 py-2 rounded-full bg-slate-100">
              <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center">
                <User className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="hidden sm:block">
                <p className="text-sm font-medium text-slate-800">
                  {user?.name || 'Teacher'}
                </p>
                <p className="text-xs text-slate-500 flex items-center gap-1">
                  <Users className="w-3 h-3" />
                  {classes.length} classes
                </p>
              </div>
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 p-4 md:p-6 space-y-4">
          {showImportState ? (
            <ImportDataState
              className={pendingClassName}
              onManualInput={handleManualInput}
              onImportComplete={handleImportComplete}
              onCancel={handleCancelImport}
            />
          ) : !activeClass && classes.length === 0 ? (
            <EmptyState onCreateClass={() => setShowAddClassModal(true)} />
          ) : showSnapshot ? (
            <SnapshotView
              classes={classes}  // ✅ Just pass as-is (string ids)
              currentMonth={currentMonth}
              currentYear={currentYear}
              defaultThresholds={defaultThresholds}
            />
          ) : showAllClasses ? (
            <AllClassesView
              classes={classes}
              onBack={() => setShowAllClasses(false)}
              onClassSelect={handleClassSelect}
              currentMonth={currentMonth}
              currentYear={currentYear}
              defaultThresholds={defaultThresholds}
            />
          ) : activeClass ? (
            <AttendanceSheet
              activeClass={activeClass}
              cls={activeClass}
              currentMonth={currentMonth}
              currentYear={currentYear}
              onAddStudent={handleAddStudent}
              onUpdateStudent={handleUpdateStudent}
              onDeleteStudent={handleDeleteStudent}
              onToggleAttendance={() => {}}
              onAddColumn={() => {}}
              onDeleteColumn={() => {}}
              defaultThresholds={{ excellent: 95, good: 90, moderate: 85, atRisk: 85 }}  // ✅ Safe defaults
              onOpenQRAttendance={handleOpenQRAttendance}
            />
          ) : null}
        </main>
      </div>

      {/* Modals */}
      <AddClassModal
        isOpen={showAddClassModal}
        className={newClassName}
        onClassNameChange={setNewClassName}
        onClose={() => {
          setShowAddClassModal(false);
          setNewClassName('');
        }}
        onCreate={handleAddClass}
      />

      <AddColumnModal
        isOpen={showAddColumnModal}
        label={newColumnLabel}
        type={newColumnType}
        onLabelChange={setNewColumnLabel}
        onTypeChange={setNewColumnType}
        onClose={() => {
          setShowAddColumnModal(false);
          setNewColumnLabel('');
          setNewColumnType('text');
        }}
        onCreate={handleAddColumn}
      />

      <DeleteClassModal
        isOpen={showDeleteClassModal}
        className={classToDelete?.name || ''}
        onClose={() => {
          setShowDeleteClassModal(false);
          setClassToDelete(null);
        }}
        onDelete={confirmDeleteClass}
      />

      {showQRModal && activeClass && (
        <QRAttendanceModal
          isOpen={showQRModal}
          classId={activeClass.id}
          className={activeClass.name}
          onClose={() => setShowQRModal(false)}
        />
      )}

      {showThresholdSettings && settingsClassId && (
        <ClassThresholdSettings
          isOpen={showThresholdSettings}
          classId={settingsClassId}
          allClasses={classes}
          thresholds={
            classes.find(c => c.id === settingsClassId)?.thresholds || defaultThresholds
          }
          onClose={() => {
            setShowThresholdSettings(false);
            setSettingsClassId(null);
          }}
          onSave={(newThresholds, applyToIds) =>
            handleSaveThresholds(newThresholds, applyToIds.map(String))
          }
        />
      )}

      <SettingsModal
        isOpen={showSettingsModal}
        onClose={() => setShowSettingsModal(false)}
        onPasswordChangeClick={handlePasswordChangeClick}
      />

      <ChangePasswordModal
        isOpen={showChangePasswordModal}
        onClose={() => setShowChangePasswordModal(false)}
      />
    </div>
  );
}
