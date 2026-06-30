/**
 *  파일명 : t_RGrid.js
 *  설  명 : AuiGrid 초기 설정 및 변수 및 메서드 생성 스크립트
 * */

var lpAuiGrid = {};

/**
 * 상수값 설정
 * */
lpAuiGrid.AuiGridStatColId = "rowStats"; // AuiGrid ROW 상태 COL ID
lpAuiGrid.AuiGridStatIns = "I"; // AuiGrid ROW 추가 상태 값
lpAuiGrid.AuiGridStatUpd = "U"; // AuiGrid ROW 수정 상태 값
lpAuiGrid.AuiGridStatDel = "D"; // AuiGrid ROW 삭제 상태 값

lpAuiGrid.AuiGridPropList = "LIST"; // AuiGrid LIST 설정 값
lpAuiGrid.AuiGridPropEdit = "EDIT"; // AuiGrid EDIT 설정 값
lpAuiGrid.AuiGridPropTree = "TREE"; // AuiGrid TREE 설정 값
//추가
//lpAuiGrid.AuiGridProp = ""; // AuiGrid EDIT 설정 값


/**
 * 그리드 기본 설정
 * */
lpAuiGrid.setInitAuiGrid = function (pGObjGrid, pProps) {

    if (AUIGrid.isCreated(pGObjGrid.myGridID)) AUIGrid.destroy(pGObjGrid.myGridID); // 삭제

     //문자 타입 숫자형 포메팅 처리
     pGObjGrid.numberFormatLabel = function (rowIndex, columnIndex, value, headerText, item) {
         if(value != undefined) return value.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
     }

    pGObjGrid.initGrid(pProps);
    lpAuiGrid.setAuiGridParam(pGObjGrid); // 그리드 파라메터 기본 설정
    lpAuiGrid.setAuiGridEvent(pGObjGrid); // 그리드 원래 이벤트 재정의
    lpAuiGrid.setAuiGridMethod(pGObjGrid); // 그리드 오브젝트 기본 사용 메서드 정의


    $(window).resize(function (e) {
       AUIGrid.resize(pGObjGrid.myGridID);
    });

    AUIGrid.resize(pGObjGrid.myGridID);

};

/**
 * 그리드 파라메터 기본 설정
 * */
lpAuiGrid.setAuiGridParam = function (pGObjGrid) {
    // 그리드
    var auiGridDefaultProps = pGObjGrid.gridParam.auiGridDefaultProps;
    var columnLayout = pGObjGrid.gridParam.columnLayout;    // 컬럼 레이아웃
    var auiGridProps = pGObjGrid.gridParam.auiGridProps;    // 그리드 속성 default속성 위에 덮어씀

    // 컬럼 레이아웃 공통 속성 정의


    // AUIGrid 를 생성 할 때 기본적으로 defaultProps 를 확장하여 생성합니다.
    var defaultProps = {
        selectionMode: "singleRow", // 선택모드[singleCell, singleRow, multipleCells, multipleRows, none]
        noDataMessage: "출력할 데이터가 없습니다.",
        headerHeight: 45,
        rowHeight: 28,
        showRowNumColumn: true,
        //fillColumnSizeMode: true,
        wrapText: true,
        usePaging: false, // 페이징 사용
        enableFilter: false,
        showPageButtonCount: 10, // 한 화면 페이징 버턴 개수 10개로 지정
        showPageRowSelect: true,
        pageRowCount: 20,   // 한 화면에 출력되는 행 개수 50개로 지정
        autoGridHeight: false,
        extraColumnOrders : ["showRowCheckColumn"], //체크박스 순서
        isRowAllCheckCurrentView : true // 필터링 된 것만 체크
    };

    switch (auiGridDefaultProps) {
        // LIST
        case lpAuiGrid.AuiGridPropList :
            defaultProps = $.extend(defaultProps, {
                enableColumnResize: true,
                enableMovingColumn: true,
                enableFilter:true,
                enableRestore : false
            });
            break;

        //EDIT
        case lpAuiGrid.AuiGridPropEdit :
            defaultProps = $.extend(defaultProps, {
                editable: true, //수정가능여부
                showStateColumn: true, // 신규,수정,삭제 아이콘 표시, default:false
                showRowCheckColumn: true, // 행 체크박스 출력여부, dafault:false
                softRemovePolicy: "exceptNew", // 사용자가 추가한 새행은 softRemoveRowMode 적용 안함. 바로 삭제함.
            });
            break;

        //TREE
        case lpAuiGrid.AuiGridPropTree :
            defaultProps = $.extend(defaultProps, {
                enableColumnResize: true,
                enableMovingColumn: true,
                // 일반 데이터를 트리로 표현할지 여부(treeIdField, treeIdRefField 설정 필수)
                flat2tree: true,
                enableFilter:true,
            });
            break;
    }

    AUIGrid.defaultProps = defaultProps;    // 기본속성으로 그리드 생성
    if(auiGridProps.enableFilter){
        var flatColumnLayout = lpAuiGrid.flatGridData(columnLayout);
        for (var i in flatColumnLayout) {
            if (!flatColumnLayout[i].hasOwnProperty("filter")) continue;
            flatColumnLayout[i].filter =  flatColumnLayout[i].filter || {};
            flatColumnLayout[i].filter.showIcon = flatColumnLayout[i].filter.showIcon || true;
            if(!auiGridProps.flat2tree){
                flatColumnLayout[i].filter.useExMenu = true // 추가적인 확장 필터 메뉴 사용
            }
        }
    }
    pGObjGrid.auiGridProps = $.extend(true, defaultProps, auiGridProps); //그리드 속성 저장
    AUIGrid.create(pGObjGrid.myGridID, columnLayout, auiGridProps);// 그리드 생성
    lpAuiGrid.hideColumnByHiddenField(pGObjGrid);   //hidden 컬럼 숨기기

        //커스텀 페이징 사용시
    if(pGObjGrid.auiGridProps.useCustomPaging) {
        pGObjGrid.selectPage = 1;
        if(!pGObjGrid.hasOwnProperty("rowCountPage")) pGObjGrid.rowCountPage = 10;
    }
};

/**
 * 그리드 원래 이벤트 재정의
 * */
lpAuiGrid.setAuiGridEvent = function (pGObjGrid) {

    let bindingEvent = pGObjGrid.setBindingEvent;
    if(pGObjGrid.setBindingEvent == undefined) bindingEvent = {};

    if(!bindingEvent.hasOwnProperty("filtering")){
        bindingEvent.filtering = function (event) {
          //필터링 이벤트 페이지에서 사용할때는 전체 선택 해제 함수 넣어줘야함
          AUIGrid.setAllCheckedRows(pGObjGrid.myGridID, false); //필터링할때는 전체 선택 해제

           //필터링 이벤트 건수변경 자동설정 넣어줘야함
          if (pGObjGrid.hasOwnProperty("allCntViewObjID")) {
              $("#" + pGObjGrid.allCntViewObjID).html(lpCom.formatNumber(AUIGrid.getRowCount(pGObjGrid.myGridID)));
          }
       }
    }

    for (var eventType in bindingEvent) {
        AUIGrid.bind(pGObjGrid.myGridID, eventType, bindingEvent[eventType]);
    }

};

/**
 * 그리드 오브젝트 기본 사용 변수, 메서드 정의
 *   -------사용 변수----------------------

 *   -------사용 메서드---------------------
 *  objGrid.setGridData(); // 데이터 로딩후 세팅
 *  pGObjGrid.addRow // 행추가
 *  pGObjGrid.removeCheckedRows // 행삭제
 *  pGObjGrid.getChgDataGrid // 변경 데이터 리턴
 *  pGObjGrid.getSelectRow// 선택 ROW 데이터 리턴
 * */

lpAuiGrid.setAuiGridMethod = function (pGObjGrid) {
    var gridParam = pGObjGrid.gridParam;

    /**
     * 그리드 초기 데이터 설정
     */
    pGObjGrid.setGridData = function (pData) {
        AUIGrid.setGridData(pGObjGrid.myGridID, pData);
        //커스텀 페이징 사용시
        if (pGObjGrid.auiGridProps.useCustomPaging) {
            var selectPage = pGObjGrid.selectPage;
            var rowCountPage = pGObjGrid.rowCountPage;
            var totalRowCount = lpCom.isEmpty(pData) ? 0 : Number(pData[0].allCnt);       // 전체 데이터 건수

            var pageButtonCount = (pGObjGrid.hasOwnProperty("pageButtonCount")) ? pGObjGrid.pageButtonCount : 10; // 페이지 네비게이션에서 보여줄 페이지의 수
            var totalPage = Math.ceil(totalRowCount / rowCountPage);    // 전체 페이지 계산

            var retStr = "";
            var prevPage = parseInt((selectPage - 1) / pageButtonCount) * pageButtonCount;
            var nextPage = ((parseInt((selectPage - 1) / pageButtonCount)) * pageButtonCount) + pageButtonCount + 1;

            prevPage = Math.max(0, prevPage);
            nextPage = Math.min(nextPage, totalPage);

            // 처음
            retStr += "<a href='javascript:"+pGObjGrid.myGridID.substr(1)+".useCustomPagingSearch(1);' class='btn_first'><span>처음</span></a>";
            // 이전
            retStr += "<a href='javascript:"+pGObjGrid.myGridID.substr(1)+".useCustomPagingSearch("+Math.max(1, prevPage)+");' class='btn_prev'><span>이전</span></a>";
            retStr += "<ul class='paging'>";

            for (var i = (prevPage + 1), len = (pageButtonCount + prevPage); i <= len; i++) {
                retStr += "<li>";
                if (selectPage == i) {
                    retStr += "<a class='on'>" + i + "</a>";
                } else {
                    retStr += "<a href='javascript:"+pGObjGrid.myGridID.substr(1)+".useCustomPagingSearch("+i+");'>"+i+"</a>";
                }
                if (i >= totalPage) {
                    break;
                }
                retStr += "</li>";
            }
            retStr += "</ul>";
            // 다음
            retStr += "<a href='javascript:"+pGObjGrid.myGridID.substr(1)+".useCustomPagingSearch("+nextPage+");' class='btn_next'><span>다음</span></a>";
            // 마지막
            retStr += "<a href='javascript:"+pGObjGrid.myGridID.substr(1)+".useCustomPagingSearch("+totalPage+");' class='btn_end'><span>끝</span></a>";
            retStr += "<label for='"+pGObjGrid.myGridID.substr(1)+"_rowCountPage' class='hidden'>페이지건수</label>";
            retStr += "<select id='"+pGObjGrid.myGridID.substr(1)+"_rowCountPage' onchange='"+pGObjGrid.myGridID.substr(1)+".useCustomPagingSearch(1);' class='form'>";
            retStr += "<option value='5' " + (rowCountPage == 5 ? 'selected' : '') + ">5</option>";
            retStr += "<option value='10' " + (rowCountPage == 10 ? 'selected' : '') + ">10</option>";
            retStr += "<option value='15'" + (rowCountPage == 15 ? 'selected' : '') + ">15</option>";
            retStr += "<option value='20'" + (rowCountPage == 20 ? 'selected' : '') + ">20</option>";
            retStr += "<option value='30'" + (rowCountPage == 30 ? 'selected' : '') + ">30</option>";
            retStr += "<option value='40'" + (rowCountPage == 40 ? 'selected' : '') + ">40</option>";
            retStr += "<option value='50'" + (rowCountPage == 50 ? 'selected' : '') + ">50</option>";
            retStr += "</select>";

            var pagingDiv = $("<div>").attr("id", "grid_paging").addClass("pagination_wrap").addClass("v_board");

            pagingDiv.append("<div class='pagination'>"+retStr+"</div>");

            $(pGObjGrid.myGridID).parent().find("#grid_paging").remove();
            $(pGObjGrid.myGridID).after(pagingDiv);
        }

        if (pGObjGrid.hasOwnProperty("allCntViewObjID")) {
            if(pGObjGrid.auiGridProps.useCustomPaging) {
                $("#" + pGObjGrid.allCntViewObjID).html(lpCom.formatNumber(lpCom.isEmpty(pData) ? 0 : pData[0].allCnt));
            } else {
                $("#" + pGObjGrid.allCntViewObjID).html(lpCom.formatNumber(pData.length));
            }
        }
        pGObjGrid.allCnt = pData.length > 0 && pData[0].hasOwnProperty("allCnt") ? pData[0].allCnt : pData.length;
        //그리드 로딩 제거
        AUIGrid.removeAjaxLoader(pGObjGrid.myGridID);

        //첫번째포커스 이동 처리(보통 처음 로딩시 적용)
        if(pGObjGrid.hasOwnProperty("isFirstRowFocus") && pGObjGrid.isFirstRowFocus){
            AUIGrid.setSelectionByIndex(pGObjGrid.myGridID, 0);
            delete pGObjGrid.isFirstRowFocus;
        }

        //마지막 변경 정보가 있으면 포커스 이동 처리
        if(pGObjGrid.lastRowId != undefined) {
            if (pGObjGrid.auiGridProps.hasOwnProperty("rowIdField") && pData.length>0) {
                //AUIGrid.selectRowsByRowId(pGObjGrid.myGridID, pGObjGrid.lastRowId);
                let rowIndex = AUIGrid.rowIdToIndex(pGObjGrid.myGridID, pGObjGrid.lastRowId);
                if(rowIndex > -1){
                    AUIGrid.setSelectionByIndex(pGObjGrid.myGridID, rowIndex);
                }
                delete pGObjGrid.lastRowId;
            }
        }
    };

    /**
     * 사용자 페이징처리 조회 함수
     */
    pGObjGrid.useCustomPagingSearch = function(pSelectPage){
       pGObjGrid.selectPage = pSelectPage;
       pGObjGrid.rowCountPage = $(pGObjGrid.myGridID+"_rowCountPage").val();

       let pageFnNm = pGObjGrid.useCustomPagingSearchNm||"fnSearch";
        try{
           if(typeof(new Function('return '+pageFnNm+'()')) != 'function' ) {
                alert(pageFnNm + "함수가 존재 하지 않습니다");
                return;
            }
            new Function('return '+pageFnNm+'()')();
        }catch(e){
            alert(pageFnNm + "함수가 존재 하지 않습니다");
        }
    }

    /**
     * 행추가
     */
    pGObjGrid.addRow = function (pRow, pRowIndex) {
        var row = {};
        if (pRow != undefined) {
            if ($.isArray(pRow)) {
                row = pRow;
            } else {
                row = pRow;
            }
        }

        var rowPos = "first";
        if (pRowIndex != undefined && pRowIndex != "") rowPos = pRowIndex;

        if (pGObjGrid.gridParam.auiGridDefaultProps != lpAuiGrid.AuiGridPropTree) {
            AUIGrid.addRow(pGObjGrid.myGridID, row, rowPos);
        } else {
            //트리일때
            AUIGrid.addTreeRow(pGObjGrid.myGridID, row, row.parentRowId, rowPos);
        }
    };


    /**
     * 선택데이터 삭제
     */
    pGObjGrid.removeCheckedRows = function () {

        var selectedItems = AUIGrid.getSelectedItems(pGObjGrid.myGridID);
        var checkedRowItems = AUIGrid.getCheckedRowItems(pGObjGrid.myGridID);

        if(selectedItems.length ==0 && checkedRowItems.length == 0){
            alert("선택된 데이터가 없습니다.");
            return;

        }

        if(checkedRowItems.length != 0){
            AUIGrid.removeCheckedRows(pGObjGrid.myGridID);
        }else{
            AUIGrid.removeRow(pGObjGrid.myGridID, "selectedIndex"); // 현재 선택된 행(들) 삭제
        }
    };

    /**
     * 변경(수정,삭제,추가) 데이터 리턴
     */
    pGObjGrid.getChgDataGrid = function () {
        // 추가된 행 아이템들(배열)
        var addedRowItems = AUIGrid.getAddedRowItems(pGObjGrid.myGridID);
        for (var i in addedRowItems) {
            addedRowItems[i][lpAuiGrid.AuiGridStatColId] = lpAuiGrid.AuiGridStatIns;
        }

        // 수정된 행 아이템들(배열) : 진짜 수정된 필드만 얻음.
        //var editedRowItems = AUIGrid.getEditedRowColumnItems(myGridID);

        // 수정된 행 아이템들(배열) : 수정된 필드와 수정안된 필드 모두를 얻음.
        var editedRowItems = AUIGrid.getEditedRowItems(pGObjGrid.myGridID);
        for (var i in editedRowItems) {
            editedRowItems[i][lpAuiGrid.AuiGridStatColId] = lpAuiGrid.AuiGridStatUpd;
        }

        // 삭제된 행 아이템들(배열)
        var removedRowItems = AUIGrid.getRemovedItems(pGObjGrid.myGridID);
        for (var i in removedRowItems) {
            removedRowItems[i][lpAuiGrid.AuiGridStatColId] = lpAuiGrid.AuiGridStatDel;
        }


        var retDataArr = [].concat(removedRowItems).concat(editedRowItems).concat(addedRowItems);

        if (pGObjGrid.gridParam.auiGridDefaultProps == lpAuiGrid.AuiGridPropTree) {
            //트리일때는 불피요 컬럼 제거 일딴 삭제 필요시.... 다시 사용
            for (var i = 0; i < retDataArr.length; i++) {
                delete retDataArr[i].children;
                delete retDataArr[i]._$depth;
                delete retDataArr[i]._$isBranch;
                delete retDataArr[i]._$isOpen;
                delete retDataArr[i]._$isVisible;
                delete retDataArr[i]._$leafCount;
                delete retDataArr[i]._$parent;
            }
        }

        return retDataArr;
    };

    /**
     * 선택 데이터 리턴
     * 다건일때는 배열로 리턴
     */
    pGObjGrid.getSelectRowData = function () {
        var selectedItems = AUIGrid.getSelectedItems(pGObjGrid.myGridID);

        var rowDataList = [];
        for (var i = 0; i < selectedItems.length; i++) {
            var rowData = selectedItems[i].item;
            rowData.columnIndex = selectedItems[i].columnIndex;
            rowData.dataField = selectedItems[i].dataField;
            rowData.rowIdValue = selectedItems[i].rowIdValue;
            rowData.rowIndex = selectedItems[i].rowIndex;

            if(AUIGrid.isAddedById(pGObjGrid.myGridID,rowData.rowIdValue)){ //추가
                rowData[lpAuiGrid.AuiGridStatColId] = lpAuiGrid.AuiGridStatIns;
            }else if(AUIGrid.isEditedById(pGObjGrid.myGridID,rowData.rowIdValue)){ //수정
                rowData[lpAuiGrid.AuiGridStatColId] = lpAuiGrid.AuiGridStatUpd;
            }else if(AUIGrid.isRemovedById(pGObjGrid.myGridID,rowData.rowIdValue)){ //삭제
                rowData[lpAuiGrid.AuiGridStatColId] = lpAuiGrid.AuiGridStatDel;
            }else{
                rowData[lpAuiGrid.AuiGridStatColId] = "";
            }

            rowDataList.push(rowData);
        }

         return rowDataList;
    };

    /**
     * 선택(체크) 데이터 리턴
     */
    pGObjGrid.getCheckedRowData = function () {
        var selectedItems = AUIGrid.getCheckedRowItems(pGObjGrid.myGridID);
        var rowDataList = [];
        for (var i = 0; i < selectedItems.length; i++) {
            var rowData = selectedItems[i].item;
            rowData.rowIndex = selectedItems[i].rowIndex;
            rowDataList.push(rowData);
        }

        return rowDataList;
    };

    /**
     * 선택(체크) 데이터 ROW_INDEX 만 리턴
     */
    pGObjGrid.getCheckedRowIndex = function () {
        var selectedItems = AUIGrid.getCheckedRowItems(pGObjGrid.myGridID);

        var rowDataList = [];
        for (var i = 0; i < selectedItems.length; i++) {
            rowDataList.push(selectedItems[i].rowIndex);
        }

        return rowDataList;
    };

    /**
     * 존재(등록,수정,미변경) 데이터만 리턴(삭제X)
     */
    pGObjGrid.getNotRemoveGridData = function () {
        var gridData = AUIGrid.getGridData(pGObjGrid.myGridID);
        var rowDataList = [];

        var rowIdCol = AUIGrid.getProp(pGObjGrid.myGridID,"rowIdField");
        for (var i = 0; i < gridData.length; i++) {
            if(!AUIGrid.isRemovedById(pGObjGrid.myGridID,gridData[i][rowIdCol])){
                rowDataList.push(gridData[i]);
            }
        }

        return rowDataList;
    };

    /**
     * 존재(등록,수정,미변경) 데이터만 리턴(삭제X)
     */
    pGObjGrid.getNotEdit = function () {
        var gridData = AUIGrid.getGridData(pGObjGrid.myGridID);
        var rowDataList = [];

        var rowIdCol = AUIGrid.getProp(pGObjGrid.myGridID,"rowIdField");
        for (var i = 0; i < gridData.length; i++) {
            if(!AUIGrid.isRemovedById(pGObjGrid.myGridID,gridData[i][rowIdCol]) && !AUIGrid.isAddedById(pGObjGrid.myGridID,gridData[i][rowIdCol])){
                rowDataList.push(gridData[i]);
            }
        }

        return rowDataList;
    };
    /**
     * rowId 값으로 데이터 변경
     */
    pGObjGrid.setRowDataByRowId = function (pRowData) {
        AUIGrid.updateRowsById(pGObjGrid.myGridID, pRowData);
    };

    /**
     * 현재 ROW 재선택 (이벤트 호출용)
     */
    pGObjGrid.currentRowSelected = function () {
        let rowIndex = AUIGrid.getSelectedIndex(pGObjGrid.myGridID)[0];
        if(rowIndex > -1){
            AUIGrid.clearSelection(pGObjGrid.myGridID);
            AUIGrid.setSelectionByIndex(pGObjGrid.myGridID, rowIndex);
        }
    };



    /**
     * 엑셀 다운로드
     */
    pGObjGrid.exportToXlsx = function (fileName, exportWithStyle) {
        exportWithStyle = exportWithStyle === undefined ? true : exportWithStyle;
        fileName = fileName === undefined ? "export" : fileName;

        AUIGrid.exportToXlsx(pGObjGrid.myGridID, {
            fileName: fileName, //파일명
            exportWithStyle: exportWithStyle, // 스타일 상태 유지 여부(기본값:true)
            exceptColumnFields: AUIGrid.getHiddenColumnDataFields(pGObjGrid.myGridID), // 숨긴 컬럼 포함 안함
        });
    };

        /**
     * pdf 다운로드
     */
    pGObjGrid.exportToPdf = function (fileName, exportWithStyle) {
        exportWithStyle = exportWithStyle === undefined ? true : exportWithStyle;
        fileName = fileName === undefined ? "export" : fileName;

        AUIGrid.exportToPdf(pGObjGrid.myGridID, {
            fileName: fileName, //파일명
            exportWithStyle: exportWithStyle, // 스타일 상태 유지 여부(기본값:true)
            exceptColumnFields: AUIGrid.getHiddenColumnDataFields(pGObjGrid.myGridID), // 숨긴 컬럼 포함 안함
            fontPath: "../fonts/NanumGothic.ttf"
        });
    };

    /**
     * 전체보기 삭제후 재생성
     */
    pGObjGrid.showAllGridData = function () {
        AUIGrid.destroy(pGObjGrid.myGridID);
        lpAuiGrid.setInitAuiGrid(pGObjGrid);
    };


    /**
     * 그리드 Validation 체크
     * {required:true, maxLength:10}
     *
     */
    pGObjGrid.validation = function () {
        var columnLayout = lpAuiGrid.flatGridData(pGObjGrid.gridParam.columnLayout);

        // required 컬럼 validation
        var requiredCols = columnLayout.reduce(function (accumulator, currentValue) {
            if (currentValue.hasOwnProperty("required") && currentValue.required === true) {
                accumulator.push(currentValue.dataField);
            }
            return accumulator;
        }, []);

        //maxLength 컬럼 validation
        var maxLengthMap = {};
        for(var i=0; i<columnLayout.length; i++){
            if(columnLayout[i].hasOwnProperty("maxLength")){
                maxLengthMap[columnLayout[i].dataField] = columnLayout[i].maxLength;
            }
        }

        if (requiredCols.length === 0 && Object.keys(maxLengthMap).length) {
            return true;
        }

        // 필수값 체크
        // 수정, 추가한 행에 대하여 전체 필드에 대하여 검사
        // var isValid = AUIGrid.validateChangedGridData(pGObjGrid.myGridID, requiredCols, "필수 항목입니다.");
        // 추가된 데이터 기준으로는 전체 컬럼 필수 입력값 체크히지만 , 미리등록된 데이터에서 필수 입력값이 아닌 다른 값을 수정후  저장 필수 입력 체크를 못함
       //  if(!isValid) return false;

        var rowIdCol = AUIGrid.getProp(pGObjGrid.myGridID,"rowIdField");

        if(rowIdCol != undefined && rowIdCol != ""){

            var chgRowList = pGObjGrid.getChgDataGrid();

            for(var i=0; i<chgRowList.length; i++){
                var rowIdVal = chgRowList[i][rowIdCol];

                //필수입력값 체크
                for(var ii=0; ii<requiredCols.length; ii++ ){
                    if(chgRowList[i].hasOwnProperty(requiredCols[ii])){
                        if($.trim(chgRowList[i][requiredCols[ii]]) == ""){
                              var rows = AUIGrid.getRowIndexesByValue(pGObjGrid.myGridID, rowIdCol, rowIdVal);
                              pGObjGrid.showToastMessageByDataField(rows, requiredCols[ii], "필수 입력 값입니다.");
                              return false;
                        }
                    }
                }

                //길이 체크
                for(var maxLengthCol in maxLengthMap){
                    if(chgRowList[i].hasOwnProperty(maxLengthCol)){
                        if(lpAuiGrid.byteCheck(chgRowList[i][maxLengthCol]) > maxLengthMap[maxLengthCol]){
                              var rows = AUIGrid.getRowIndexesByValue(pGObjGrid.myGridID, rowIdCol, rowIdVal);
                              pGObjGrid.showToastMessageByDataField(rows, maxLengthCol, "최대 길이("+maxLengthMap[maxLengthCol]+"Byte)를 초과 하였습니다.");
                              return false;
                        }
                    }

                }

            }
        }

        return true;
    };

    /**
     * 해당 조건과 일치 하는  ROW 데이터 리턴
     * 예) ObjGrid.getFindRowData({COL_NM:VALUE})
     */
    pGObjGrid.getFindRowData = function (pCond) {
        var rowDatas = AUIGrid.getOrgGridData(pGObjGrid.myGridID);

        var fRowData = {};
        for (var i = 0; i < rowDatas.length; i++) {
            var isFind = true;
            for (var key in pCond) {
                if (rowDatas[i][key] != pCond[key]) {
                    isFind = false;
                    break;
                }
            }
            if (isFind) {
                fRowData = rowDatas[i];
                fRowData.rowIndex = i;
                break;
            }
        }

        return fRowData;
    };

    /**
     * 선택 로우 데이터 가져오기
     */
    pGObjGrid.getSelectedRowItems = function (msg) {
        return AUIGrid.getSelectedItems(pGObjGrid.myGridID)[0];
    };

    /**
     * empty 그리드 데이터 생성
     */
    pGObjGrid.getEmptyItem = function (exclude) {
        if(lpCom.isEmpty(exclude)) exclude = [];

        var data = lpAuiGrid.flatGridData(pGObjGrid.gridParam.columnLayout);
        var emptyItem = {};
        for (var i in data) {
            var field = data[i].dataField;

            if(exclude.indexOf(field) > -1) continue;

            if((data[i].hasOwnProperty("dataType")) && data[i].dataType === "numeric") {
                emptyItem[field] = 0;
            } else {
                emptyItem[field] = '';
            }
        }

        return emptyItem;
    };

    /**
     * row 위치 변경 되기전 이벤트 체크
     */
    pGObjGrid.isAfterRowPosition = function(pEvent,pMsg){

        if(pEvent.rowIndex  == -1) return true;

        let rowMap = AUIGrid.getItemByRowIndex(pGObjGrid.myGridID,pEvent.rowIndex);
        let rowId = rowMap.gridRowId;

        if((AUIGrid.isEditedById(pGObjGrid.myGridID,rowId) || AUIGrid.isAddedById(pGObjGrid.myGridID,rowId))
             && pEvent.rowIndex != pEvent.toRowIndex
             ){
              if(!confirm(pMsg)){
                  return false;
              }
         }

         if(pEvent.rowIndex != pEvent.toRowIndex){
            if(AUIGrid.isAddedById(pGObjGrid.myGridID,rowId)){

              if((AUIGrid.getRowCount(pGObjGrid.myGridID) -1) != pEvent.rowIndex  || pEvent.rowIndex-1 != pEvent.toRowIndex ) {
                 pGObjGrid.selectionChangePause = true;    //마지막 ROW가아닐때만
              }
              AUIGrid.removeRow(pGObjGrid.myGridID,pEvent.rowIndex);
              pGObjGrid.selectionChangePause = false;
            }else{
                AUIGrid.restoreEditedRows(pGObjGrid.myGridID, pEvent.rowIndex );
            }
         }
         return true;
    }

    /**
     * ToastMessage 표시
     */
    pGObjGrid.showToastMessage = function (rowIndex , colIndex , msg) {
        rowIndex = rowIndex || 0;
        colIndex = colIndex || 0;
        AUIGrid.showToastMessage(pGObjGrid.myGridID, rowIndex, colIndex, msg);
    };

    /*
     * * ToastMessage 표시 데이터 필드값으로
     */
    pGObjGrid.showToastMessageByDataField = function (rowIndex , dataField , msg) {
        var colIndex = AUIGrid.getColumnIndexByDataField(pGObjGrid.myGridID, dataField);

        rowIndex = rowIndex || 0;
        colIndex = colIndex || 0;
        AUIGrid.showToastMessage(pGObjGrid.myGridID, rowIndex, colIndex, msg);
    };
};
/**
 * 그리드 공통 사용 메서드 정의
 *
 * */

/**
 * hidden 필드 가 true일 경우 해당 컬럼 숨김 처리
 */
lpAuiGrid.hideColumnByHiddenField = function (pGObjGrid) {
    var columnLayout = lpAuiGrid.flatGridData(pGObjGrid.gridParam.columnLayout);


    // hidden 컬럼 숨기기
    var hideCols = columnLayout.reduce(function (accumulator, currentValue) {
        if (currentValue.hasOwnProperty("hidden") && currentValue.hidden === true || currentValue.hidden == "true") {
            accumulator.push(currentValue.dataField);
        }
        return accumulator;
    }, []);

    AUIGrid.hideColumnByDataField(pGObjGrid.myGridID, hideCols);
};

/**
 * DropDownListRenderer 리턴
 */
lpAuiGrid.getDropDownListRenderer = function (codeList) {
    var renderer = {
        type: "DropDownListRenderer",
        list: codeList,
        keyField: "cd", // key 에 해당되는 필드명
        valueField: "cdNm" // value 에 해당되는 필드명
    };

    return renderer;
};

/**
 * columnLayout dataFieldf를 가진 1차원 배열로 반환
 */
lpAuiGrid.flatGridData = function(list) {
    var toReturn = [];

    for (var i in list) {
        if(list[i].hasOwnProperty("children")) {
            var flatList =  lpAuiGrid.flatGridData(list[i].children);
            toReturn = toReturn.concat(flatList);
        } else if(list[i].hasOwnProperty("dataField")) {
            toReturn.push(list[i]);
        }
    }

    return toReturn;
};

/**
 * 바이트 계산
 */
lpAuiGrid.byteCheck = function(pVal){
    var codeByte = 0;
    for (var idx = 0; idx < pVal.length; idx++) {
        var oneChar = escape(pVal.charAt(idx));
        if ( oneChar.length == 1 ) {
            codeByte ++;
        } else if (oneChar.indexOf("%u") != -1) {
            codeByte += 2; // 오라클 한글 2바이트 인식
        } else if (oneChar.indexOf("%") != -1) {
            codeByte ++;
        }
    }
    return codeByte;
}

/**
 *  selectBox 설정(검색가능)
 *  lpAuiGrid.setComboBox(this,"DEPT_ID",lpCom.setUserCodeSelect("",{cond:{condId:"CN01"},first:"X"}));
 */
lpAuiGrid.setComboBox = function(pAuiGrid,pDataField,pSelectFunc,pListTemplateFunction){
    var rowDataList = pSelectFunc;
    pAuiGrid[pDataField+"ComboData"]  = {};
    for(var i=0;i<rowDataList.length; i++){
       pAuiGrid[pDataField+"ComboData"][rowDataList[i].cd] = rowDataList[i];
    }


     var columnLayout = null;
     for(var i=0; i<pAuiGrid.gridParam.columnLayout.length; i++){
         if(pAuiGrid.gridParam.columnLayout[i].dataField == pDataField){
             columnLayout = pAuiGrid.gridParam.columnLayout[i];
             break;
         }
         //children
         if (pAuiGrid.gridParam.columnLayout[i].children != undefined) {
             for (let j = 0; j < pAuiGrid.gridParam.columnLayout[i].children.length; j++) {
                 if (pAuiGrid.gridParam.columnLayout[i].children[j].dataField == pDataField) {
                     columnLayout = pAuiGrid.gridParam.columnLayout[i].children[j];
                     break;
                 }
             }
         }
     }

     if(columnLayout !=null){
        columnLayout.labelFunction = function(  rowIndex, columnIndex, value, headerText, item ) {
            var retStr = "";
            if(pAuiGrid[pDataField+"ComboData"].hasOwnProperty(value)){
                retStr = pAuiGrid[pDataField+"ComboData"][value].cdNm;
            }
            return retStr == "" ? value : retStr;
        };

         //dataField obj에 comboNum 속성 있는 경우, rowData cdNm : cd.cdNm 으로 변경
         if (columnLayout.comboNum != undefined) {
             for (var i = 0; i < rowDataList.length; i++) {
                 if (rowDataList[i].cd != "") {
                     if (columnLayout.comboNum == "cd") rowDataList[i].cdNm = rowDataList[i].cd + "." + rowDataList[i].cdNm;
                     if (columnLayout.comboNum == "num") rowDataList[i].cdNm = (i + 1) + "." + rowDataList[i].cdNm
                 }
             }
         }

        columnLayout.editRenderer = {
            type : "ComboBoxRenderer"
           , autoCompleteMode : true // 자동완성 모드 설정
           , matchFromFirst : false // 처음부터 매치가 아닌 단순 포함되는 자동완성
           , autoEasyMode: true
           , list : rowDataList //key-value Object 로 구성된 리스트
           , keyField : "cd" // key 에 해당되는 필드명
           , valueField : "cdNm" // value 에 해당되는 필드명
           , showEditorBtnOver : true // 마우스 오버 시 에디터버턴 보이기
           , validator: function (oldValue, newValue, item, dataField, fromClipboard, which) {
                let isValidate = $(".aui-grid-drop-list-ul>li").length == 0 && newValue !="" ? false : true;
                return { "validate": isValidate, "message": "리스트에 있는 값만 선택(입력) 가능합니다." };
            }
           , listTemplateFunction : function(rowIndex, columnIndex, text, item, dataField, listItem) {
                var html = '<div style="text-align :left;" width="30" height="20" >'+ listItem.cdNm+'</div>';
                return html;
           }
        };

        if(pListTemplateFunction !=undefined){
            columnLayout.editRenderer.listTemplateFunction = pListTemplateFunction;
        }
    }
 }

/**
 * selectBox 설정 - 화면 콤보 선택 아이콘 보임
 *  lpAuiGrid.setDropDownList(this,"DEPT_ID",lpCom.setUserCodeSelect("",{cond:{COND_ID:"CN01"},first:"X"}));
 */
lpAuiGrid.setDropDownList = function(pAuiGrid,pDataField,pSelectFunc){

    pAuiGrid[pDataField+"ComboData"] = pSelectFunc;

    var columnLayout = null;
    for(var i=0; i<pAuiGrid.gridParam.columnLayout.length; i++){
        if(pAuiGrid.gridParam.columnLayout[i].dataField == pDataField){
            columnLayout = pAuiGrid.gridParam.columnLayout[i];
            break;
        }
        //children
        if (pAuiGrid.gridParam.columnLayout[i].children != undefined) {
            for (let j = 0; j < pAuiGrid.gridParam.columnLayout[i].children.length; j++) {
                if (pAuiGrid.gridParam.columnLayout[i].children[j].dataField == pDataField) {
                    columnLayout = pAuiGrid.gridParam.columnLayout[i].children[j];
                    break;
                }
            }
        }
    }

    if(columnLayout !=null){
        columnLayout.renderer = { type: "DropDownListRenderer",
                                  list: pAuiGrid[pDataField+"ComboData"],
                                  keyField: "cd", // key 에 해당되는 필드명
                                  valueField: "cdNm", // value 에 해당되는 필드명
                                  showEditorBtnOver : true // 마우스 오버 시 에디터버턴 보이기
                               }
    }
}

/**
 * selectBox 설정
 *  lpAuiGrid.setDropDownList2(this,"DEPT_ID",lpCom.setUserCodeSelect("",{cond:{COND_ID:"CN01"},first:"X"}));
 */
lpAuiGrid.setDropDownList2 = function(pAuiGrid,pDataField,pSelectFunc){

    var rowDataList = pSelectFunc;
    pAuiGrid[pDataField+"ComboData"]  = {};
    for(var i=0;i<rowDataList.length; i++){
       pAuiGrid[pDataField+"ComboData"][rowDataList[i].cd] = rowDataList[i];
    }


    var columnLayout = null;
    for(var i=0; i<pAuiGrid.gridParam.columnLayout.length; i++){
        if(pAuiGrid.gridParam.columnLayout[i].dataField == pDataField){
            columnLayout = pAuiGrid.gridParam.columnLayout[i];
            break;
        }
        //children
        if (pAuiGrid.gridParam.columnLayout[i].children != undefined) {
            for (let j = 0; j < pAuiGrid.gridParam.columnLayout[i].children.length; j++) {
                if (pAuiGrid.gridParam.columnLayout[i].children[j].dataField == pDataField) {
                    columnLayout = pAuiGrid.gridParam.columnLayout[i].children[j];
                    break;
                }
            }
        }
    }

    if(columnLayout !=null){
       columnLayout.labelFunction = function(  rowIndex, columnIndex, value, headerText, item ) {
            var retStr = "";
            if(pAuiGrid[pDataField+"ComboData"].hasOwnProperty(value)){
                retStr = pAuiGrid[pDataField+"ComboData"][value].cdNm;
            }
            return retStr == "" ? value : retStr;
        };

        columnLayout.editRenderer = {
                type: "DropDownListRenderer",
                showEditorBtnOver : true, // 마우스 오버 시 에디터버턴 보이기
                list: rowDataList,
                keyField: "cd", // key 에 해당되는 필드명
                valueField: "cdNm", // value 에 해당되는 필드명
        }
    }
}



/**
 * selectBox 멀티 선택 설정
 *  lpAuiGrid.setMultipleDropDownList(this,"DEPT_ID",lpCom.setUserCodeSelect("",{cond:{COND_ID:"CN01"},first:"X"}));
 */
lpAuiGrid.setMultipleDropDownList = function(pAuiGrid,pDataField,pSelectFunc){

    var rowDataList = pSelectFunc;
    pAuiGrid[pDataField+"ComboDatas"] = rowDataList;
    var columnLayout = null;
    for(var i=0; i<pAuiGrid.gridParam.columnLayout.length; i++){
        if(pAuiGrid.gridParam.columnLayout[i].dataField == pDataField){
            columnLayout = pAuiGrid.gridParam.columnLayout[i];
            break;
        }
    }

    if(columnLayout !=null){
       columnLayout.labelFunction = function(  rowIndex, columnIndex, value, headerText, item ) {
            var retArr = [];
            let comboDatas = pAuiGrid[pDataField+"ComboDatas"];
            for(let i=0; i<comboDatas.length; i++){
                 const regex = new RegExp(`\\b${comboDatas[i].cd}\\b`, 'gi');
                 if(regex.test(value)){
                    retArr.push(comboDatas[i].cdNm);
                 }
            }

            return retArr.length == 0 ? value : retArr.join(", ");
        };

        columnLayout.editRenderer = {
                type: "DropDownListRenderer",
                showEditorBtnOver : true, // 마우스 오버 시 에디터버턴 보이기
                list: rowDataList,
                keyField: "cd", // key 에 해당되는 필드명
                valueField: "cdNm", // value 에 해당되는 필드명
                multipleMode:true
        }
    }
}



